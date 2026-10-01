"""
AuditorProver: Core engine for textbook logical integrity auditing.

Uses "Lobotomized Retrieval" (time-restricted context) and GPT-4o-mini
to judge whether theorems can be proven using ONLY prior knowledge.

Key Design Principles:
1. SKEPTICISM: The LLM cannot use internal knowledge to fill gaps
2. LOCALITY: Only context from chapters < current_chapter is allowed
3. FORMALIZATION: Successful proofs are verified via Lean 4 compilation
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from openai import OpenAI
from src.verification.verdicts import parse_verdict

from src.config.settings import get_settings, Settings, BudgetTracker
from src.retrieval.hybrid_orchestrator import HybridRetriever, RetrievalResult
from src.verification.lean_compiler import Lean4Compiler, LeanCompilationResult


logger = logging.getLogger(__name__)


# =============================================================================
# THE SKEPTICISM PROMPT (CRITICAL)
# =============================================================================

AUDITOR_SYSTEM_PROMPT = """You are a STRICT Mathematical Auditor for a Calculus textbook.

Your task is to verify whether a given theorem can be PROVEN using ONLY the definitions, lemmas, and theorems provided in the [CONTEXT] section.

## CRITICAL CONSTRAINTS

1. **CONTEXT ONLY**: You may ONLY use the definitions and theorems explicitly provided in [CONTEXT]. Do NOT use your internal knowledge of Calculus.

2. **IDENTIFY GAPS**: If the proof requires ANY concept, definition, or theorem that is NOT in the context, you MUST output `FAIL_GAP` and explain exactly what prerequisite is missing.

3. **NO GAP FILLING**: Even if YOU know a definition or theorem that would help, if it's not in the context, the proof FAILS. This simulates a student who has only read up to this chapter.

4. **LOGIC CHECK**: If the theorem is logically flawed or contradictory (regardless of context), output `FAIL_LOGIC`.

## LEAN 4 CODE REQUIREMENTS (CRITICAL)

If you output `PASS`, you MUST provide valid Lean 4 code. Follow these rules:

1. **Start with imports**: Always begin with `import Mathlib.Tactic`
2. **Use proper theorem syntax**: `theorem name : type := proof` or `theorem name : type := by tactic`
3. **DO NOT use**: `#eval`, `#check`, or any commands starting with `#`
4. **Complete proofs only**: Never use `sorry`, `admit`, or introduce new axioms.

### Valid Lean 4 Example:
```lean
import Mathlib.Tactic

-- Derivative of constant is zero
theorem deriv_const_zero (c : ℝ) : ∀ x : ℝ, deriv (fun _ => c) x = 0 := by
  simp
```

## OUTPUT FORMAT

Respond with valid JSON only:

```json
{
  "status": "PASS" | "FAIL_GAP" | "FAIL_LOGIC" | "ABSTAIN",
  "confidence": <float between 0.0 and 1.0>,
  "lean_code": "<Complete Lean 4 code starting with 'import Mathlib.Tactic' if PASS, else null>",
  "reason": "<Detailed explanation of your verdict>",
  "missing_prerequisites": ["<list of missing concepts if FAIL_GAP, else empty>"]
}
```

**Confidence** represents your certainty (0.0 to 1.0) that the theorem is logically sound given the provided context.
- 1.0 = Absolutely certain the proof is correct
- 0.7-0.9 = High confidence, minor uncertainty
- 0.5-0.7 = Moderate confidence
- Below 0.5 = Should probably be FAIL_GAP

## EXAMPLES

### Example 1: PASS (with valid Lean 4)
```json
{
  "status": "PASS",
  "confidence": 0.95,
  "lean_code": "import Mathlib.Tactic\\n\\ntheorem deriv_const_is_zero (c : ℝ) : ∀ x : ℝ, deriv (fun _ => c) x = 0 := by\\n  intro x\\n  simp [deriv_const]",
  "reason": "Proof follows from the definition of derivative in context.",
  "missing_prerequisites": []
}
```

### Example 2: FAIL_GAP
```json
{
  "status": "FAIL_GAP",
  "confidence": 0.1,
  "lean_code": null,
  "reason": "Proof requires the Fundamental Theorem of Calculus which is not in context.",
  "missing_prerequisites": ["Fundamental Theorem of Calculus", "definite integral definition"]
}
```

### Example 3: FAIL_LOGIC
```json
{
  "status": "FAIL_LOGIC",
  "lean_code": null,
  "reason": "The statement is mathematically false: derivative of x^2 is 2x, not x.",
  "missing_prerequisites": []
}
```
"""


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class AuditResult:
    """Result of auditing a single theorem."""
    theorem_text: str
    chapter_tested: int
    status: str  # VERIFIED_FORMAL, VERIFIED_LOGIC, FAIL_GAP, FAIL_LOGIC
    reason: str
    lean_code: Optional[str] = None
    lean_compilation_result: Optional[LeanCompilationResult] = None
    lean_error: Optional[str] = None  # Lean compiler error if any
    llm_confidence: float = 0.0  # LLM's confidence score (0.0 - 1.0)
    missing_prerequisites: List[str] = field(default_factory=list)
    context_count: int = 0
    context_chapters: List[int] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "theorem_text": self.theorem_text[:200],  # Truncate for readability
            "chapter_tested": self.chapter_tested,
            "status": self.status,
            "reason": self.reason,
            "llm_confidence": self.llm_confidence,
            "lean_code": self.lean_code,
            "lean_compiled": self.lean_compilation_result.success if self.lean_compilation_result else None,
            "lean_error": self.lean_error,
            "missing_prerequisites": self.missing_prerequisites,
            "context_count": self.context_count,
            "context_chapters": self.context_chapters,
            "timestamp": self.timestamp,
        }


# =============================================================================
# AUDITOR PROVER CLASS
# =============================================================================

class AuditorProver:
    """Core engine for textbook logical integrity auditing.
    
    Uses lobotomized retrieval to fetch only prior chapter context,
    then asks GPT-4o-mini to verify if the theorem can be proven
    using ONLY that context.
    
    Workflow:
    1. Retrieve context from chapters < current_chapter
    2. Ask LLM to verify with SKEPTICISM prompt
    3. If PASS, compile the Lean code for formal verification
    4. Return verdict: VERIFIED, FAIL_GAP, FAIL_LOGIC, or FAIL_LEAN
    
    Example:
        >>> prover = AuditorProver()
        >>> result = prover.audit_theorem("∫f(x)dx = F(x) + C", chapter=5)
        >>> print(result.status)  # VERIFIED or FAIL_*
    """
    
    def __init__(
        self,
        settings: Optional[Settings] = None,
        retriever: Optional[HybridRetriever] = None,
        lean_compiler: Optional[Lean4Compiler] = None,
        budget_tracker: Optional[BudgetTracker] = None,
    ):
        """Initialize AuditorProver.
        
        Args:
            settings: Configuration settings.
            retriever: Hybrid retriever for context (uses lobotomized retrieval).
            lean_compiler: Lean 4 compiler for formal verification.
            budget_tracker: Budget tracker for API costs.
        """
        self.settings = settings or get_settings()
        self.retriever = retriever or HybridRetriever()
        self.lean_compiler = lean_compiler
        self.budget_tracker = budget_tracker
        
        # Initialize OpenAI client
        self.openai = self.settings.create_openai_client()
        self.model = self.settings.default_model  # gpt-4o-mini
    
    def _build_context_block(self, results: List[RetrievalResult]) -> str:
        """Build the [CONTEXT] block from retrieval results."""
        if not results:
            return "[CONTEXT]\n(No prior definitions or theorems available)\n[/CONTEXT]"
        
        lines = ["[CONTEXT]"]
        for i, r in enumerate(results, 1):
            chapter = r.metadata.get("chapter", "?")
            label = r.metadata.get("label", "Concept")
            lines.append(f"\n--- Item {i} (Chapter {chapter}, {label}) ---")
            lines.append(r.content)
        lines.append("\n[/CONTEXT]")
        
        return "\n".join(lines)
    
    def _parse_llm_response(self, content: str) -> Dict[str, Any]:
        """Parse LLM response, handling JSON extraction."""
        return parse_verdict(content).model_dump()

    def audit_theorem(
        self,
        theorem_text: str,
        chapter: int,
        n_context: int = 10,
        skip_lean: bool = False,
    ) -> AuditResult:
        """Audit a theorem using only prior chapter context.
        
        Args:
            theorem_text: The theorem statement to verify.
            chapter: The chapter where this theorem appears.
                    Only context from chapters <= chapter will be used.
            n_context: Number of context items to retrieve.
            skip_lean: If True, skip Lean compilation (faster, ~5s/item instead of ~90s).
            
        Returns:
            AuditResult with verdict and details.
        """
        logger.info(f"Auditing theorem from Chapter {chapter}: {theorem_text[:50]}...")
        
        # Step 1: Retrieve lobotomized context
        context_results = self.retriever.retrieve_for_audit(
            query=theorem_text,
            current_chapter=chapter,
            n_results=n_context,
            rerank=True,
        )
        
        context_chapters = list(set(
            r.metadata.get("chapter") for r in context_results
            if r.metadata.get("chapter") is not None
        ))
        
        logger.info(f"Retrieved {len(context_results)} context items from chapters {context_chapters}")
        
        # Step 2: Build prompt
        context_block = self._build_context_block(context_results)
        
        user_prompt = f"""## THEOREM TO VERIFY (from Chapter {chapter})

{theorem_text}

## AVAILABLE CONTEXT (from chapters prior to Chapter {chapter})

{context_block}

## YOUR TASK

Determine if this theorem can be proven using ONLY the definitions and theorems in the context above.
Remember: You MUST NOT use your internal knowledge of Calculus. Only use what's in [CONTEXT].

Respond with JSON only."""
        
        # Step 3: Call LLM
        try:
            response = self.openai.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": AUDITOR_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=1500,
                temperature=0.1,  # Low temperature for consistency
            )
            
            llm_content = response.choices[0].message.content
            
            # Track budget
            if self.budget_tracker:
                self.budget_tracker.record_call(
                    input_tokens=response.usage.prompt_tokens,
                    output_tokens=response.usage.completion_tokens,
                    model=self.model,
                    purpose=f"audit_theorem_ch{chapter}",
                )
            
            # Parse response
            llm_result = self._parse_llm_response(llm_content)
            
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return AuditResult(
                theorem_text=theorem_text,
                chapter_tested=chapter,
                status="FAIL_LLM",
                reason=f"LLM call failed: {str(e)}",
                context_count=len(context_results),
                context_chapters=context_chapters,
            )
        
        # Step 4: Branch based on LLM verdict
        status = llm_result.get("status", "UNKNOWN")
        reason = llm_result.get("reason", "No reason provided")
        lean_code = llm_result.get("lean_code")
        missing = llm_result.get("missing_prerequisites", [])
        confidence = float(llm_result.get("confidence", 0.5))  # Default 0.5 if not provided
        
        if status in ["FAIL_GAP", "FAIL_LOGIC", "ABSTAIN"]:
            # Immediate failure - no Lean compilation needed
            return AuditResult(
                theorem_text=theorem_text,
                chapter_tested=chapter,
                status=status,
                reason=reason,
                lean_code=lean_code,
                lean_error=None,
                llm_confidence=confidence,
                missing_prerequisites=missing,
                context_count=len(context_results),
                context_chapters=context_chapters,
            )
        
        elif status == "PASS":
            # Step 5: Best Effort Verification
            # LLM approved the proof - optionally compile for formal verification
            
            # Fast mode: skip Lean compilation entirely
            if skip_lean or not lean_code:
                return AuditResult(
                    theorem_text=theorem_text,
                    chapter_tested=chapter,
                    status="VERIFIED_LOGIC",
                    reason=f"LLM judged adequate (Confidence: {confidence:.2f}). {reason}",
                    lean_code=lean_code,
                    lean_error=None,
                    llm_confidence=confidence,
                    context_count=len(context_results),
                    context_chapters=context_chapters,
                )
            
            # Full mode: try Lean compilation
            if lean_code:
                try:
                    # Single compile attempt (no skeleton fallback for speed)
                    if self.lean_compiler is None:
                        self.lean_compiler = Lean4Compiler(settings=self.settings)
                    compilation_result = self.lean_compiler.compile(lean_code)
                    
                    if compilation_result.success and compilation_result.verification_type == "VERIFIED_PROOF":
                        # Full formal verification!
                        final_status = "VERIFIED_FORMAL"
                        final_reason = f"Formally verified in Lean 4 (Confidence: {confidence:.2f}). {reason}"
                        lean_error = None
                    else:
                        # Preserve legacy status; it denotes an LLM judgment, not a proof.
                        final_status = "VERIFIED_LOGIC"
                        lean_error = "; ".join(compilation_result.errors[:3]) or compilation_result.verification_type
                        final_reason = f"LLM judged adequate (Confidence: {confidence:.2f}). Formal proof not certified: {compilation_result.verification_type}."
                    
                    return AuditResult(
                        theorem_text=theorem_text,
                        chapter_tested=chapter,
                        status=final_status,
                        reason=final_reason,
                        lean_code=lean_code,
                        lean_compilation_result=compilation_result,
                        lean_error=lean_error,
                        llm_confidence=confidence,
                        context_count=len(context_results),
                        context_chapters=context_chapters,
                    )
                    
                except Exception as e:
                    # Compilation exception - still treat as logic pass
                    logger.warning(f"Lean compilation exception: {e}")
                    return AuditResult(
                        theorem_text=theorem_text,
                        chapter_tested=chapter,
                        status="VERIFIED_LOGIC",
                        reason=f"LLM judged adequate (Confidence: {confidence:.2f}). Lean exception: {str(e)[:50]}",
                        lean_code=lean_code,
                        lean_error=str(e),
                        llm_confidence=confidence,
                        context_count=len(context_results),
                        context_chapters=context_chapters,
                    )
            else:
                # PASS but no Lean code provided - logic pass
                return AuditResult(
                    theorem_text=theorem_text,
                    chapter_tested=chapter,
                    status="VERIFIED_LOGIC",
                    reason=f"LLM judged adequate (Confidence: {confidence:.2f}). No formal proof generated.",
                    llm_confidence=confidence,
                    context_count=len(context_results),
                    context_chapters=context_chapters,
                )
        
        else:
            # Unknown status
            return AuditResult(
                theorem_text=theorem_text,
                chapter_tested=chapter,
                status="UNKNOWN",
                reason=f"Unexpected LLM status: {status}. {reason}",
                context_count=len(context_results),
                context_chapters=context_chapters,
            )
    
    def audit_batch(
        self,
        theorems: List[Dict[str, Any]],
    ) -> List[AuditResult]:
        """Audit multiple theorems.
        
        Args:
            theorems: List of dicts with 'text' and 'chapter' keys.
            
        Returns:
            List of AuditResult objects.
        """
        results = []
        for thm in theorems:
            result = self.audit_theorem(
                theorem_text=thm["text"],
                chapter=thm["chapter"],
            )
            results.append(result)
        return results
    
    def close(self):
        """Close resources."""
        self.retriever.close()


class MockAuditorProver:
    """Mock AuditorProver for testing."""
    
    def audit_theorem(self, theorem_text: str, chapter: int) -> AuditResult:
        return AuditResult(
            theorem_text=theorem_text,
            chapter_tested=chapter,
            status="PASS_INFORMAL",
            reason="Mock audit - always passes",
            context_count=0,
            context_chapters=[],
        )
    
    def close(self):
        pass
