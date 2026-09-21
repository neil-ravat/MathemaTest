"""
MCQ Generation Engine for MathemaTest.

Uses GPT-4o with Reasoning Packets from hybrid retrieval to generate
verified, diagnostic multiple-choice questions with symbolic validation.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime

from openai import OpenAI

from src.config.settings import get_settings, Settings, BudgetTracker
from src.retrieval.hybrid_orchestrator import HybridRetriever, ReasoningPacket
from src.verification.verification_sandbox import SymbolicVerifier, VerificationResult


logger = logging.getLogger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class MCQOption:
    """A single MCQ option."""
    label: str  # A, B, C, D
    content: str  # The answer text/LaTeX
    is_correct: bool
    explanation: Optional[str] = None


@dataclass 
class GeneratedMCQ:
    """A complete generated MCQ with verification status."""
    id: str
    question: str
    question_latex: Optional[str]
    options: List[MCQOption]
    correct_answer: str
    explanation: str
    solution_steps: List[str]
    difficulty: str  # easy, medium, hard
    topic: str
    prerequisites: List[str]
    misconceptions_addressed: List[str]
    
    # Verification metadata
    is_verified: bool = False
    verification_attempts: int = 0
    verification_errors: List[str] = field(default_factory=list)
    confidence_score: float = 0.0
    
    # Lean 4 formalization (Semester VI hook)
    lean4_theorem: Optional[str] = None
    
    # Source tracking
    source_concepts: List[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "id": self.id,
            "question": self.question,
            "question_latex": self.question_latex,
            "options": [
                {
                    "label": o.label,
                    "content": o.content,
                    "is_correct": o.is_correct,
                    "explanation": o.explanation,
                }
                for o in self.options
            ],
            "correct_answer": self.correct_answer,
            "explanation": self.explanation,
            "solution_steps": self.solution_steps,
            "difficulty": self.difficulty,
            "topic": self.topic,
            "prerequisites": self.prerequisites,
            "misconceptions_addressed": self.misconceptions_addressed,
            "is_verified": self.is_verified,
            "verification_attempts": self.verification_attempts,
            "confidence_score": self.confidence_score,
            "lean4_theorem": self.lean4_theorem,
            "source_concepts": self.source_concepts,
            "generated_at": self.generated_at,
        }


# =============================================================================
# PROMPTS
# =============================================================================

MCQ_GENERATION_SYSTEM_PROMPT = """You are an expert STEM educator creating diagnostic multiple-choice questions. Your MCQs must:

1. Test deep conceptual understanding, not just memorization
2. Include ONE clearly correct answer
3. Include 3 plausible distractors - EACH MUST be based on a SPECIFIC misconception
4. Be mathematically precise with correct notation

=== CRITICAL: ENFORCED MISCONCEPTION-BASED DISTRACTORS ===

**MANDATORY DISTRACTOR REQUIREMENTS:**
Each of the 3 distractors (wrong answers) MUST correspond to a specific misconception:
- If a misconception is provided from the graph, use it directly
- If no misconception exists, create a "Synthetic Misconception" based on:
  * Forgetting a prerequisite step (e.g., "Forgot the chain rule")
  * Sign/direction error (e.g., "Reversed the inequality")
  * Unit confusion (e.g., "Mixed radians and degrees")
  * Off-by-one error (e.g., "Counted endpoints incorrectly")
  * Formula component swap (e.g., "Swapped numerator and denominator")

**PURE MATH ONLY in options and correct_answer:**
- The `options` values must contain ONLY the mathematical expression
- NO explanatory text, NO "(correct)", NO "where...", NO descriptions
- NO LaTeX delimiters ($, \\(, \\)) inside the JSON string values
- Use simple notation: "ad - bc" NOT "$ad - bc$ (this is correct)"
- For fractions: "1/3" or "(a*b)/(c*d)" NOT "\\frac{1}{3}"
- For exponents: "x^2" or "e^x" NOT LaTeX notation
- For roots: "sqrt(2)" NOT "\\sqrt{2}"
- For trig: "sin(x)" or "2*cos(x)" NOT "\\sin(x)"

**GOOD Examples:**
- "ad - bc"
- "1/3"  
- "2, 3" (for multiple roots)
- "pi*i"
- "e^x * sin(x)"
- "-2"

**BAD Examples (NEVER DO THIS):**
- "$ad - bc$ (correct)"
- "\\frac{1}{3}"
- "x = 2 or x = 3"
- "$2x \\cos(x^2)$"

OUTPUT FORMAT (JSON):
{
  "question": "Clear question text with LaTeX where needed ($...$)",
  "question_latex": "Any pure LaTeX expressions in the question",
  "options": {
    "A": "PURE_MATH_ONLY",
    "B": "PURE_MATH_ONLY",
    "C": "PURE_MATH_ONLY",
    "D": "PURE_MATH_ONLY"
  },
  "correct_answer": "A|B|C|D",
  "explanation": "Detailed explanation of the correct answer",
  "solution_steps": [
    "Step 1: ...",
    "Step 2: ...",
    "Final answer: ..."
  ],
  "difficulty": "easy|medium|hard",
  "topic": "Main topic being tested",
  "prerequisites": ["Required prior knowledge"],
  "misconceptions_targeted": [
    {
      "option": "B",
      "misconception_source": "graph|synthetic",
      "misconception": "REQUIRED: Specific student error this distractor catches",
      "prerequisite_gap": "If synthetic: which prerequisite was forgotten"
    },
    {
      "option": "C",
      "misconception_source": "graph|synthetic",
      "misconception": "REQUIRED: Specific student error this distractor catches",
      "prerequisite_gap": "If synthetic: which prerequisite was forgotten"
    },
    {
      "option": "D",
      "misconception_source": "graph|synthetic",
      "misconception": "REQUIRED: Specific student error this distractor catches",
      "prerequisite_gap": "If synthetic: which prerequisite was forgotten"
    }
  ]
}

DISTRACTOR GUIDELINES (STRICT):
- EVERY distractor MUST have a documented misconception
- Each misconception must be plausible and diagnostic
- Sign errors, unit confusion, formula misapplication are common patterns
- Make distractors numerically plausible (not obviously wrong)
- Never make two options equivalent

Respond with valid JSON only."""


def create_mcq_prompt(
    topic: str,
    context_packet: ReasoningPacket,
    misconceptions: List[Dict[str, str]],
    difficulty: str = "medium",
) -> str:
    """Create the MCQ generation prompt.
    
    Args:
        topic: Topic to generate question about.
        context_packet: Retrieved context from hybrid search.
        misconceptions: List of misconceptions from graph.
        difficulty: Target difficulty level.
        
    Returns:
        Formatted prompt string.
    """
    # Format retrieved content
    context_parts = []
    for result in context_packet.results[:5]:
        context_parts.append(f"- {result.content}")
    context_str = "\n".join(context_parts)
    
    # Format misconceptions
    misc_parts = []
    for misc in misconceptions[:5]:
        misc_parts.append(f"- {misc.get('description', '')}: {misc.get('common_error', '')}")
    misc_str = "\n".join(misc_parts) if misc_parts else "No specific misconceptions provided"
    
    return f"""Generate a {difficulty}-level MCQ about: {topic}

RETRIEVED CONTEXT:
{context_str}

KNOWN STUDENT MISCONCEPTIONS TO TARGET:
{misc_str}

REQUIREMENTS:
- Question should test understanding of the concept, not just recall
- Use the misconceptions above to create diagnostic distractors
- Include clear LaTeX for any mathematical expressions
- Provide step-by-step solution

Generate the MCQ as JSON."""


# =============================================================================
# MCQ GENERATOR
# =============================================================================

class MCQGenerator:
    """Generates verified MCQs using GPT-4o with symbolic validation.
    
    Workflow:
    1. Retrieve context via HybridRetriever
    2. Generate MCQ via GPT-4o
    3. Verify with SymPy
    4. Self-correct if verification fails
    5. Output only verified MCQs
    
    Example:
        >>> generator = MCQGenerator()
        >>> mcq = generator.generate("Work-Energy Theorem", difficulty="medium")
        >>> if mcq.is_verified:
        ...     print(mcq.to_dict())
    """
    
    MAX_VERIFICATION_ATTEMPTS = 3
    
    def __init__(
        self,
        settings: Optional[Settings] = None,
        retriever: Optional[HybridRetriever] = None,
        verifier: Optional[SymbolicVerifier] = None,
        budget_tracker: Optional[BudgetTracker] = None,
    ):
        """Initialize MCQ generator.
        
        Args:
            settings: Configuration settings.
            retriever: Hybrid retriever for context.
            verifier: Symbolic verifier.
            budget_tracker: Budget tracker for API costs.
        """
        self.settings = settings or get_settings()
        self.retriever = retriever
        self.verifier = verifier or SymbolicVerifier()
        self.budget_tracker = budget_tracker or BudgetTracker(self.settings)
        
        if self.settings.validate_openai_key():
            self.openai = self.settings.create_openai_client()
        else:
            self.openai = None
            logger.warning("OpenAI API key not configured")
    
    def _generate_raw_mcq(
        self,
        topic: str,
        context: ReasoningPacket,
        misconceptions: List[Dict],
        difficulty: str,
        correction_feedback: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Generate raw MCQ via GPT-4o.
        
        Args:
            topic: Topic for MCQ.
            context: Retrieved context.
            misconceptions: Known misconceptions.
            difficulty: Target difficulty.
            correction_feedback: Feedback for self-correction.
            
        Returns:
            Parsed MCQ dict or None.
        """
        if not self.openai:
            logger.error("OpenAI client not initialized")
            return None
        
        prompt = create_mcq_prompt(topic, context, misconceptions, difficulty)
        
        if correction_feedback:
            prompt += f"\n\nPREVIOUS ATTEMPT FAILED VERIFICATION:\n{correction_feedback}\n\nPlease fix the issues and regenerate."
        
        try:
            response = self.openai.chat.completions.create(
                model=self.settings.gpt4o_model,  # Using GPT-4o for quality
                messages=[
                    {"role": "system", "content": MCQ_GENERATION_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=2000,
                response_format={"type": "json_object"},
            )
            
            usage = response.usage
            self.budget_tracker.record_call(
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                model=self.settings.gpt4o_model,
                purpose=f"MCQ generation: {topic}",
            )
            
            return json.loads(response.choices[0].message.content)
            
        except Exception as e:
            logger.error(f"MCQ generation failed: {e}")
            return None
    
    def _verify_mcq(self, mcq_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Verify MCQ mathematical correctness.
        
        Args:
            mcq_data: Raw MCQ data.
            
        Returns:
            Tuple of (is_valid, list of error messages).
        """
        errors = []
        
        # Get correct answer content
        correct_label = mcq_data.get("correct_answer", "A")
        options = mcq_data.get("options", {})
        correct_content = options.get(correct_label, "")
        
        # Get distractor contents
        distractors = [
            content for label, content in options.items()
            if label != correct_label
        ]
        
        # Verify correct answer can be parsed
        if mcq_data.get("question_latex"):
            correct_result = self.verifier.verify_parse(correct_content)
            if not correct_result.is_valid:
                errors.append(f"Correct answer parse error: {correct_result.error_message}")
        
        # Verify distractors are different from correct
        for i, distractor in enumerate(distractors):
            equiv_result = self.verifier.verify_equivalence(correct_content, distractor)
            if equiv_result.is_valid:
                errors.append(f"Distractor {i+1} is equivalent to correct answer")
        
        # Check solution steps are present
        if not mcq_data.get("solution_steps"):
            errors.append("Missing solution steps")
        
        return len(errors) == 0, errors
    
    def _create_mcq_object(
        self,
        mcq_data: Dict[str, Any],
        topic: str,
        is_verified: bool,
        attempts: int,
        errors: List[str],
        misconceptions: List[Dict],
    ) -> GeneratedMCQ:
        """Convert raw MCQ data to GeneratedMCQ object.
        
        Args:
            mcq_data: Raw MCQ dict.
            topic: Topic of the MCQ.
            is_verified: Verification status.
            attempts: Number of verification attempts.
            errors: Any verification errors.
            misconceptions: Misconceptions addressed.
            
        Returns:
            GeneratedMCQ object.
        """
        options_dict = mcq_data.get("options", {})
        correct_label = mcq_data.get("correct_answer", "A")
        
        options = [
            MCQOption(
                label=label,
                content=content,
                is_correct=(label == correct_label),
                explanation=self._get_distractor_explanation(
                    label, mcq_data.get("misconceptions_targeted", [])
                ) if label != correct_label else None,
            )
            for label, content in options_dict.items()
        ]
        
        # Calculate confidence based on verification
        confidence = 1.0 if is_verified else 0.5 - (attempts * 0.1)
        
        return GeneratedMCQ(
            id=f"mcq_{topic.replace(' ', '_').lower()}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            question=mcq_data.get("question", ""),
            question_latex=mcq_data.get("question_latex"),
            options=options,
            correct_answer=correct_label,
            explanation=mcq_data.get("explanation", ""),
            solution_steps=mcq_data.get("solution_steps", []),
            difficulty=mcq_data.get("difficulty", "medium"),
            topic=mcq_data.get("topic", topic),
            prerequisites=mcq_data.get("prerequisites", []),
            misconceptions_addressed=[m.get("misconception", "") for m in mcq_data.get("misconceptions_targeted", [])],
            is_verified=is_verified,
            verification_attempts=attempts,
            verification_errors=errors,
            confidence_score=confidence,
            source_concepts=[topic],
        )
    
    def _get_distractor_explanation(
        self,
        label: str,
        misconceptions: List[Dict],
    ) -> Optional[str]:
        """Get explanation for a distractor based on misconceptions.
        
        Args:
            label: Option label.
            misconceptions: List of misconceptions with option mappings.
            
        Returns:
            Explanation string or None.
        """
        for misc in misconceptions:
            if misc.get("option") == label:
                return misc.get("misconception")
        return None
    
    def generate(
        self,
        topic: str,
        difficulty: str = "medium",
        use_retrieval: bool = True,
    ) -> Optional[GeneratedMCQ]:
        """Generate a verified MCQ on the given topic.
        
        Implements the verification loop:
        1. Generate MCQ
        2. Verify with SymPy
        3. If failed, self-correct up to MAX_ATTEMPTS
        4. Return only if verified
        
        Args:
            topic: Topic for the MCQ.
            difficulty: easy, medium, or hard.
            use_retrieval: Whether to use hybrid retrieval.
            
        Returns:
            Verified GeneratedMCQ or None if verification fails.
        """
        logger.info(f"Generating MCQ for: {topic} (difficulty: {difficulty})")
        
        # Step 1: Retrieve context
        if use_retrieval and self.retriever:
            context = self.retriever.retrieve(topic, n_results=5)
            misconceptions = [
                r.metadata for r in context.results
                if r.metadata.get("type") == "misconception"
            ]
        else:
            # Mock context
            from src.retrieval.hybrid_orchestrator import ReasoningPacket, RetrievalResult
            context = ReasoningPacket(
                query=topic,
                refined_query=topic,
                results=[],
                graph_context={},
                total_results=0,
                vector_count=0,
                graph_count=0,
            )
            misconceptions = []
        
        # Step 2-4: Generate and verify loop
        attempts = 0
        all_errors = []
        correction_feedback = None
        
        while attempts < self.MAX_VERIFICATION_ATTEMPTS:
            attempts += 1
            logger.info(f"Generation attempt {attempts}/{self.MAX_VERIFICATION_ATTEMPTS}")
            
            # Generate
            mcq_data = self._generate_raw_mcq(
                topic=topic,
                context=context,
                misconceptions=misconceptions,
                difficulty=difficulty,
                correction_feedback=correction_feedback,
            )
            
            if not mcq_data:
                all_errors.append(f"Attempt {attempts}: Generation failed")
                continue
            
            # Verify
            is_valid, errors = self._verify_mcq(mcq_data)
            
            if is_valid:
                logger.info("✓ MCQ verified successfully")
                return self._create_mcq_object(
                    mcq_data=mcq_data,
                    topic=topic,
                    is_verified=True,
                    attempts=attempts,
                    errors=[],
                    misconceptions=misconceptions,
                )
            else:
                logger.warning(f"✗ Verification failed: {errors}")
                all_errors.extend(errors)
                correction_feedback = "\n".join(errors)
        
        # All attempts failed - return unverified MCQ with warning
        logger.error(f"MCQ verification failed after {attempts} attempts")
        
        if mcq_data:
            return self._create_mcq_object(
                mcq_data=mcq_data,
                topic=topic,
                is_verified=False,
                attempts=attempts,
                errors=all_errors,
                misconceptions=misconceptions,
            )
        
        return None
    
    def generate_batch(
        self,
        topics: List[str],
        difficulty: str = "medium",
        verified_only: bool = True,
    ) -> List[GeneratedMCQ]:
        """Generate multiple MCQs.
        
        Args:
            topics: List of topics.
            difficulty: Target difficulty.
            verified_only: Only return verified MCQs.
            
        Returns:
            List of GeneratedMCQ objects.
        """
        results = []
        
        for topic in topics:
            mcq = self.generate(topic, difficulty)
            if mcq:
                if verified_only and not mcq.is_verified:
                    logger.warning(f"Skipping unverified MCQ: {topic}")
                    continue
                results.append(mcq)
        
        return results
    
    def export_to_json(
        self,
        mcqs: List[GeneratedMCQ],
        output_path: str,
    ) -> int:
        """Export MCQs to JSON file.
        
        Args:
            mcqs: List of MCQs to export.
            output_path: Output file path.
            
        Returns:
            Number of MCQs exported.
        """
        output = {
            "generated_at": datetime.now().isoformat(),
            "total_mcqs": len(mcqs),
            "verified_count": sum(1 for m in mcqs if m.is_verified),
            "mcqs": [m.to_dict() for m in mcqs],
        }
        
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2)
        
        logger.info(f"Exported {len(mcqs)} MCQs to {output_path}")
        return len(mcqs)


class MockMCQGenerator:
    """Mock MCQ generator for testing."""
    
    def generate(self, topic: str, difficulty: str = "medium", **kwargs) -> GeneratedMCQ:
        return GeneratedMCQ(
            id=f"mock_mcq_{topic}",
            question=f"What is the definition of {topic}?",
            question_latex=None,
            options=[
                MCQOption("A", "Correct answer", True),
                MCQOption("B", "Wrong answer 1", False),
                MCQOption("C", "Wrong answer 2", False),
                MCQOption("D", "Wrong answer 3", False),
            ],
            correct_answer="A",
            explanation="This is the correct explanation",
            solution_steps=["Step 1", "Step 2"],
            difficulty=difficulty,
            topic=topic,
            prerequisites=[],
            misconceptions_addressed=[],
            is_verified=True,
            confidence_score=0.95,
        )
    
    def generate_batch(self, topics: list, **kwargs) -> list:
        return [self.generate(t) for t in topics]

from typing import Tuple
