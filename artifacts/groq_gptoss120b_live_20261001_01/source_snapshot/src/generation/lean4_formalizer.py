"""
Lean 4 Formalization for MathemaTest (Mathlib-Aware Version).

Converts mathematical expressions and theorems to Lean 4 format
for formal verification with full Mathlib support.

Phase C Task 3: Every generated .lean file MUST start with `import Mathlib`.
"""

from __future__ import annotations

import re
import logging
from typing import Optional, Dict, Any, List

from openai import OpenAI

from src.config.settings import get_settings, Settings, BudgetTracker


logger = logging.getLogger(__name__)


# Mathlib-aware formalization prompt with tactic context
LEAN4_MATHLIB_PROMPT = """You are an expert Lean 4 mathematician using Mathlib. Convert this mathematical statement to a verified Lean 4 theorem.

MATHEMATICAL STATEMENT:
{statement}

CORRECT ANSWER:
{answer}

=== MATHLIB TACTIC REFERENCE ===

**Arithmetic & Algebra:**
- `ring` : Proves polynomial identities automatically
- `ring_nf` : Normalize ring expressions  
- `field_simp` : Simplify field expressions (handles division)
- `linarith` : Linear arithmetic goals

**Sets & Logic:**
- `ext` : Extensionality (for sets, functions)
- `decide` : Decidable propositions
- `tauto` : Propositional tautologies
- `push_neg` : Push negations inward
- `contrapose` : Contrapositive reasoning

**Numbers:**
- `norm_num` : Numeric normalization (3 + 5 = 8)
- `omega` : Linear arithmetic over ℤ and ℕ
- `positivity` : Prove expressions are positive/negative

**Analysis:**
- `continuity` : Prove continuity
- `measurability` : Prove measurability  
- `norm_cast` : Coercion normalization

**Complex Numbers:**
- Use `Complex.abs` for |z| (NOT bare `abs`)
- Use `Complex.normSq` for |z|²
- Use `Complex.I` for the imaginary unit

**Sets & Bounds:**
- `lowerBounds` and `upperBounds` take a Set as argument
- For ordered fields, use `le_refl`, `le_trans`
- `Set.mem_setOf` for membership in set comprehensions

=== REQUIREMENTS ===

1. ALWAYS start with: `import Mathlib`
2. Use `open` statements for common namespaces
3. Prefer automation tactics when possible (`ring`, `linarith`, `norm_num`)
4. For complex proofs, use `sorry` as placeholder
5. For absolute value of complex: `Complex.abs z` NOT `|z|` or `abs z`

=== OUTPUT FORMAT ===

```lean
import Mathlib

open Real Complex Set

theorem generated_theorem : [statement] := by
  [tactics or sorry]
```

Output ONLY valid Lean 4 code. No explanations."""


# Common mathematical patterns to Lean 4
LATEX_TO_LEAN_PATTERNS = [
    (r"\\frac\{([^}]+)\}\{([^}]+)\}", r"(\1) / (\2)"),
    (r"\^2", r"^2"),
    (r"\^{([^}]+)}", r"^(\1)"),
    (r"\\sqrt\{([^}]+)\}", r"Real.sqrt (\1)"),
    (r"\\int", r"∫"),
    (r"\\sum", r"∑"),
    (r"\\prod", r"∏"),
    (r"\\forall", r"∀"),
    (r"\\exists", r"∃"),
    (r"\\in", r"∈"),
    (r"\\subset", r"⊂"),
    (r"\\cup", r"∪"),
    (r"\\cap", r"∩"),
    (r"\\neq", r"≠"),
    (r"\\leq", r"≤"),
    (r"\\geq", r"≥"),
    (r"\\to", r"→"),
    (r"\\implies", r"→"),
    (r"\\iff", r"↔"),
    (r"\\land", r"∧"),
    (r"\\lor", r"∨"),
    (r"\\neg", r"¬"),
    (r"\\alpha", r"α"),
    (r"\\beta", r"β"),
    (r"\\gamma", r"γ"),
    (r"\\delta", r"δ"),
    (r"\\pi", r"π"),
]


# Common Mathlib imports
MATHLIB_PRELUDE = """import Mathlib

open Real Complex Set Function
open scoped BigOperators

"""


class Lean4Formalizer:
    """Generates Mathlib-aware Lean 4 theorem statements.
    
    Every generated .lean file starts with `import Mathlib` and uses
    appropriate Mathlib tactics for the domain.
    
    Example:
        >>> formalizer = Lean4Formalizer()
        >>> lean_code = formalizer.formalize("x^2 - 4 = 0", "x = 2 or x = -2")
    """
    
    def __init__(
        self,
        settings: Optional[Settings] = None,
        budget_tracker: Optional[BudgetTracker] = None,
    ):
        """Initialize formalizer.
        
        Args:
            settings: Configuration settings.
            budget_tracker: Budget tracker for API calls.
        """
        self.settings = settings or get_settings()
        self.budget_tracker = budget_tracker or BudgetTracker(self.settings)
        
        if self.settings.validate_openai_key():
            self.openai = self.settings.create_openai_client()
        else:
            self.openai = None
    
    def latex_to_lean_basic(self, latex: str) -> str:
        """Basic LaTeX to Lean conversion (symbolic only).
        
        Args:
            latex: LaTeX expression.
            
        Returns:
            Lean-compatible string.
        """
        result = latex
        for pattern, replacement in LATEX_TO_LEAN_PATTERNS:
            result = re.sub(pattern, replacement, result)
        return result
    
    def get_domain_hints(self, statement: str) -> List[str]:
        """Detect mathematical domain and return relevant hints.
        
        Args:
            statement: The mathematical statement.
            
        Returns:
            List of domain-specific hints for the prompt.
        """
        statement_lower = statement.lower()
        hints = []
        
        if any(kw in statement_lower for kw in ["complex", "imaginary", "|z|", "modulus"]):
            hints.append("Use Complex.abs for |z|, Complex.normSq for |z|², Complex.I for i")
        
        if any(kw in statement_lower for kw in ["polynomial", "x^2", "x^3", "roots"]):
            hints.append("Use ring tactic for polynomial identities")
        
        if any(kw in statement_lower for kw in ["integer", "divisible", "prime", "mod"]):
            hints.append("Use omega for linear integer arithmetic, Int.emod for modular")
        
        if any(kw in statement_lower for kw in ["set", "subset", "union", "intersection"]):
            hints.append("Use ext for set equality, Set.mem_setOf for membership")
        
        if any(kw in statement_lower for kw in ["bound", "supremum", "infimum", "least"]):
            hints.append("Use lowerBounds and upperBounds with Set arguments")
        
        if any(kw in statement_lower for kw in ["continuous", "derivative", "limit"]):
            hints.append("Use continuity tactic, or HasDerivAt for derivatives")
        
        return hints
    
    def formalize(
        self,
        statement: str,
        answer: str,
        topic: str = "",
        with_proof: bool = False,
    ) -> Optional[str]:
        """Generate Mathlib-aware Lean 4 theorem statement.
        
        Args:
            statement: Mathematical statement/question.
            answer: Correct answer.
            topic: Topic name for theorem naming.
            with_proof: Whether to attempt proof generation.
            
        Returns:
            Lean 4 code starting with `import Mathlib`, or None.
        """
        if not self.openai:
            # Return basic formalization
            return self._basic_formalize(statement, answer, topic)
        
        try:
            # Get domain-specific hints
            hints = self.get_domain_hints(statement)
            hint_text = "\n".join(f"- {h}" for h in hints) if hints else "No specific hints."
            
            prompt = LEAN4_MATHLIB_PROMPT.format(
                statement=statement,
                answer=answer,
            )
            
            # Add domain hints
            if hints:
                prompt += f"\n\n=== DOMAIN-SPECIFIC HINTS ===\n{hint_text}"
            
            response = self.openai.chat.completions.create(
                model=self.settings.default_model,  # GPT-4o-mini for budget
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=600,
            )
            
            usage = response.usage
            if hasattr(self.budget_tracker, 'record_call'):
                self.budget_tracker.record_call(
                    input_tokens=usage.prompt_tokens,
                    output_tokens=usage.completion_tokens,
                    model=self.settings.default_model,
                    purpose="lean4_formalization",
                )
            
            content = response.choices[0].message.content.strip()
            
            # Extract code from markdown blocks
            if "```lean" in content:
                content = content.split("```lean")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            # Ensure it starts with import Mathlib
            if not content.strip().startswith("import Mathlib"):
                content = "import Mathlib\n\n" + content
            
            return content.strip()
            
        except Exception as e:
            logger.error(f"Lean 4 formalization failed: {e}")
            return self._basic_formalize(statement, answer, topic)
    
    def _basic_formalize(
        self,
        statement: str,
        answer: str,
        topic: str,
    ) -> str:
        """Generate basic Lean 4 template without API.
        
        Args:
            statement: Mathematical statement.
            answer: Correct answer.
            topic: Topic for naming.
            
        Returns:
            Basic Lean 4 theorem skeleton with import Mathlib.
        """
        # Clean topic for theorem name
        name = re.sub(r"[^a-zA-Z0-9_]", "_", topic.lower())[:30] if topic else "unnamed"
        
        lean_statement = self.latex_to_lean_basic(statement)
        lean_answer = self.latex_to_lean_basic(answer)
        
        return f"""import Mathlib

open Real Complex Set

-- MathemaTest Generated Theorem
-- Topic: {topic}
-- Statement: {statement}
-- Answer: {answer}

theorem mathematest_{name} :
  -- TODO: Formalize this statement
  -- Original: {lean_statement}
  -- Answer: {lean_answer}
  True := by
  sorry
"""
    
    def formalize_mcq(self, mcq: Dict[str, Any]) -> str:
        """Formalize an MCQ to Lean 4.
        
        Args:
            mcq: MCQ dictionary with question, options, correct_answer.
            
        Returns:
            Lean 4 theorem statement with import Mathlib.
        """
        question = mcq.get("question", "")
        correct_label = mcq.get("correct_answer", "A")
        options = mcq.get("options", {})
        correct = options.get(correct_label, "") if isinstance(options, dict) else ""
        
        # If options is a list, find correct one
        if isinstance(options, list):
            for opt in options:
                if opt.get("is_correct"):
                    correct = opt.get("content", "")
                    break
        
        return self.formalize(
            statement=question,
            answer=correct,
            topic=mcq.get("topic", ""),
        )
    
    def formalize_aime_problem(self, problem: Dict[str, Any]) -> str:
        """Formalize an AIME problem to Lean 4.
        
        Args:
            problem: Problem dictionary with 'problem' and 'type' fields.
            
        Returns:
            Lean 4 theorem statement.
        """
        return self.formalize(
            statement=problem.get("problem", ""),
            answer="",  # AIME problems don't have pre-defined answers
            topic=f"aime_{problem.get('type', 'unknown')}",
        )


class MockLean4Formalizer:
    """Mock formalizer for testing."""
    
    def formalize(self, statement: str, answer: str, topic: str = "") -> str:
        return f"""import Mathlib

-- Mock Lean 4 theorem for: {topic}
theorem mock_theorem : True := by trivial
"""
    
    def formalize_mcq(self, mcq: Dict) -> str:
        return self.formalize("", "", mcq.get("topic", ""))
