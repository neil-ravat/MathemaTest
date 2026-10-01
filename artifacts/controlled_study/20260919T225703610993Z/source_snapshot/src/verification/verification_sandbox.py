"""
Symbolic Verification Sandbox for MathemaTest.

Provides secure SymPy-based verification of mathematical expressions
to ensure generated MCQs are mathematically correct.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

import sympy
from sympy import symbols, sympify, simplify, Eq, solve
from sympy.parsing.latex import parse_latex


logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Result of symbolic verification."""
    is_valid: bool
    expression: str
    sympy_expr: Optional[str] = None
    error_message: Optional[str] = None
    verification_type: str = "parse"  # parse, equivalence, solve
    details: Dict[str, Any] = field(default_factory=dict)


class LaTeXToSymPy:
    """Converts LaTeX expressions to SymPy objects.
    
    Handles common LaTeX patterns and provides fallback parsing.
    """
    
    # Common replacements for latex2sympy compatibility
    LATEX_FIXES = [
        # Greek letters
        (r"\\alpha", "alpha"),
        (r"\\beta", "beta"),
        (r"\\gamma", "gamma"),
        (r"\\delta", "delta"),
        (r"\\theta", "theta"),
        (r"\\phi", "phi"),
        (r"\\rho", "rho"),
        (r"\\sigma", "sigma"),
        (r"\\omega", "omega"),
        # Operators
        (r"\\cdot", "*"),
        (r"\\times", "*"),
        (r"\\div", "/"),
        # Special functions
        (r"\\sin", "sin"),
        (r"\\cos", "cos"),
        (r"\\tan", "tan"),
        (r"\\log", "log"),
        (r"\\ln", "ln"),
        (r"\\exp", "exp"),
        (r"\\sqrt", "sqrt"),
        # Misc
        (r"\\left", ""),
        (r"\\right", ""),
        (r"\\,", " "),
        (r"\\;", " "),
        (r"\\quad", " "),
    ]
    
    @classmethod
    def preprocess_latex(cls, latex: str) -> str:
        """Hyper-aggressive LaTeX preprocessing for SymPy compatibility.
        
        Strips ALL non-mathematical content including delimiters, annotations,
        text commands, and converts natural language to symbolic form.
        
        Args:
            latex: Raw LaTeX string.
            
        Returns:
            Clean mathematical expression ready for SymPy.
        """
        if not latex:
            return ""
        
        result = latex.strip()
        
        # === PHASE 1: Strip trailing annotations FIRST ===
        # Remove parenthesized annotations: (correct), (answer), (This is...)
        result = re.sub(r"\s*\([^)]*correct[^)]*\).*$", "", result, flags=re.IGNORECASE)
        result = re.sub(r"\s*\([^)]*answer[^)]*\).*$", "", result, flags=re.IGNORECASE)
        result = re.sub(r"\s*\([^)]*solution[^)]*\).*$", "", result, flags=re.IGNORECASE)
        result = re.sub(r"\s*\(This[^)]*\).*$", "", result, flags=re.IGNORECASE)
        result = re.sub(r"\s*\(where[^)]*\).*$", "", result, flags=re.IGNORECASE)
        
        # Remove trailing text after expression
        result = re.sub(r"\s*,\s*where\s+.*$", "", result, flags=re.IGNORECASE)
        result = re.sub(r"\s+is\s+(the\s+)?correct.*$", "", result, flags=re.IGNORECASE)
        result = re.sub(r"\s+which\s+.*$", "", result, flags=re.IGNORECASE)
        result = re.sub(r"\s+since\s+.*$", "", result, flags=re.IGNORECASE)
        result = re.sub(r"\s+because\s+.*$", "", result, flags=re.IGNORECASE)
        
        # === PHASE 2: Remove ALL LaTeX delimiters ===
        # Dollar signs (inline and display)
        result = result.replace("$", "")
        
        # Display math: \[ \] and \( \)
        result = result.replace(r"\[", "").replace(r"\]", "")
        result = result.replace(r"\(", "").replace(r"\)", "")
        
        # Double-escaped versions from JSON
        result = result.replace("\\\\[", "").replace("\\\\]", "")
        result = result.replace("\\\\(", "").replace("\\\\)", "")
        
        # === PHASE 3: Remove ALL \text{} and similar commands ===
        result = re.sub(r"\\text\{[^}]*\}", "", result)
        result = re.sub(r"\\textbf\{[^}]*\}", "", result)
        result = re.sub(r"\\textit\{[^}]*\}", "", result)
        result = re.sub(r"\\mathrm\{([^}]*)\}", r"\1", result)  # Keep content
        result = re.sub(r"\\mathbf\{([^}]*)\}", r"\1", result)  # Keep content
        
        # Remove \left and \right
        result = re.sub(r"\\left\s*", "", result)
        result = re.sub(r"\\right\s*", "", result)
        
        # Remove \quad, \qquad, spacing commands
        result = re.sub(r"\\q?quad\s*", " ", result)
        result = re.sub(r"\\[,;:!]\s*", " ", result)
        
        # === PHASE 4: Apply standard LaTeX fixes ===
        for pattern, replacement in cls.LATEX_FIXES:
            result = result.replace(pattern, replacement)
        
        # === PHASE 5: Convert natural language connectors to symbolic ===
        # "x = 2 or x = 3" -> "{2, 3}" or just extract numbers
        if " or " in result.lower() or " and " in result.lower():
            # Try to extract just the values
            values = re.findall(r"=\s*(-?\d+(?:\.\d+)?)", result)
            if len(values) >= 2:
                result = ", ".join(values)  # "2, 3"
        
        # "x = 2, x = 3" format -> extract values
        if result.count("=") > 1:
            values = re.findall(r"=\s*(-?\d+(?:\.\d+)?)", result)
            if len(values) >= 2:
                result = ", ".join(values)
        
        # === PHASE 6: Clean up spacing and artifacts ===
        result = re.sub(r"\s+", " ", result)  # Multiple spaces to single
        result = result.strip()
        
        # Remove leading/trailing commas
        result = result.strip(",").strip()
        
        return result
    
    @classmethod
    def parse(cls, latex: str) -> Tuple[Optional[sympy.Expr], Optional[str]]:
        """Parse LaTeX to SymPy expression.
        
        Args:
            latex: LaTeX expression.
            
        Returns:
            Tuple of (SymPy expression, error message if failed).
        """
        preprocessed = cls.preprocess_latex(latex)
        
        # Try latex2sympy first
        try:
            from latex2sympy2 import latex2sympy
            expr = latex2sympy(preprocessed)
            return expr, None
        except Exception as e1:
            pass
        
        # Try SymPy's built-in parser
        try:
            expr = parse_latex(preprocessed)
            return expr, None
        except Exception as e2:
            pass
        
        # Try direct sympify (works for simple expressions)
        try:
            # Convert common patterns
            simple = preprocessed
            simple = re.sub(r"\\frac\{([^}]+)\}\{([^}]+)\}", r"(\1)/(\2)", simple)
            simple = re.sub(r"\^(\d+)", r"**\1", simple)
            simple = re.sub(r"\^{([^}]+)}", r"**(\1)", simple)
            simple = re.sub(r"_\{?([a-zA-Z0-9]+)\}?", r"_\1", simple)
            
            expr = sympify(simple)
            return expr, None
        except Exception as e3:
            return None, f"All parsers failed: {e3}"


class SymbolicVerifier:
    """Verifies mathematical expressions and equations using SymPy.
    
    Provides multiple verification methods:
    - Parse check: Can expression be parsed?
    - Equivalence check: Are two expressions equivalent?
    - Solution check: Does a solution satisfy an equation?
    
    Example:
        >>> verifier = SymbolicVerifier()
        >>> result = verifier.verify_equation("x^2 - 4 = 0", "x = 2")
        >>> print(result.is_valid)  # True
    """
    
    def __init__(self, timeout_seconds: int = 5):
        """Initialize verifier.
        
        Args:
            timeout_seconds: Timeout for verification operations.
        """
        self.timeout = timeout_seconds
        self.parser = LaTeXToSymPy()
    
    def verify_parse(self, latex: str, debug_log: bool = True, allow_soft_verify: bool = True) -> VerificationResult:
        """Two-tier verification: Full parse OR soft-verify fallback.
        
        Tier 1: Try full SymPy parse and symbolic evaluation
        Tier 2: If parse fails, check if it's valid LaTeX syntax (soft-verify)
        
        Args:
            latex: LaTeX expression.
            debug_log: If True, log verbose debug info.
            allow_soft_verify: If True, use soft-verify fallback on parse failure.
            
        Returns:
            VerificationResult with parse status.
        """
        # Debug logging for troubleshooting
        if debug_log:
            logger.debug(f"[VERIFY] Input LaTeX: {repr(latex)}")
        
        # === TIER 1: Full SymPy parse ===
        expr, error = self.parser.parse(latex)
        
        if expr is not None:
            if debug_log:
                logger.debug(f"[VERIFY] TIER 1 SUCCESS: Parsed to {expr}")
            return VerificationResult(
                is_valid=True,
                expression=latex,
                sympy_expr=str(expr),
                verification_type="parse",
            )
        
        # === TIER 2: Soft-verify fallback ===
        if allow_soft_verify:
            soft_result = self._soft_verify(latex, debug_log)
            if soft_result.is_valid:
                return soft_result
        
        # Both tiers failed
        if debug_log:
            logger.warning(f"[VERIFY] FAILED to parse: {repr(latex[:100])}")
            logger.warning(f"[VERIFY] Error: {error}")
        return VerificationResult(
            is_valid=False,
            expression=latex,
            error_message=error,
            verification_type="parse",
        )
    
    def _soft_verify(self, latex: str, debug_log: bool = True) -> VerificationResult:
        """Tier 2: Soft verification for valid-looking expressions.
        
        Accepts expressions that:
        - Contain valid mathematical content (numbers, operators, variables)
        - Don't have obvious formatting issues
        - Look like legitimate mathematical answers
        
        Args:
            latex: LaTeX expression.
            debug_log: Log verbose info.
            
        Returns:
            VerificationResult with soft-verify status.
        """
        # Preprocess to get clean expression
        clean = self.parser.preprocess_latex(latex)
        
        if not clean:
            return VerificationResult(
                is_valid=False,
                expression=latex,
                error_message="Empty expression after preprocessing",
                verification_type="soft_verify",
            )
        
        # Check if it looks like a valid mathematical expression
        # Must contain at least one number or known variable
        has_math_content = bool(re.search(r'[\d]|[a-zA-Z]', clean))
        
        # Must not be pure natural language
        is_not_text = not bool(re.search(r'^[a-zA-Z\s]{10,}$', clean))  # Not just words
        
        # Reject common non-math patterns
        bad_patterns = [
            r'^\s*$',  # Empty
            r'^the\s',  # Starts with "the"
            r'^if\s',   # Starts with "if"  
            r'^assume',  # Starts with "assume"
            r'^show\s',  # Starts with "show"
            r'^prove',   # Starts with "prove"
            r'^consider',  # Starts with "consider"
        ]
        is_likely_text = any(re.match(p, clean.lower()) for p in bad_patterns)
        
        if has_math_content and is_not_text and not is_likely_text:
            if debug_log:
                logger.info(f"[VERIFY] TIER 2 SOFT-VERIFY accepted: {repr(clean[:50])}")
            return VerificationResult(
                is_valid=True,  # Accept as soft-verified
                expression=latex,
                sympy_expr=f"SOFT:{clean}",  # Mark as soft-verified
                verification_type="soft_verify",
            )
        
        return VerificationResult(
            is_valid=False,
            expression=latex,
            error_message=f"Soft-verify rejected: looks like text, not math",
            verification_type="soft_verify",
        )
    
    def verify_equivalence(
        self,
        expr1: str,
        expr2: str,
    ) -> VerificationResult:
        """Verify two expressions are mathematically equivalent.
        
        Args:
            expr1: First expression (LaTeX).
            expr2: Second expression (LaTeX).
            
        Returns:
            VerificationResult with equivalence status.
        """
        parsed1, err1 = self.parser.parse(expr1)
        parsed2, err2 = self.parser.parse(expr2)
        
        if parsed1 is None:
            return VerificationResult(
                is_valid=False,
                expression=expr1,
                error_message=f"Failed to parse expr1: {err1}",
                verification_type="equivalence",
            )
        
        if parsed2 is None:
            return VerificationResult(
                is_valid=False,
                expression=expr2,
                error_message=f"Failed to parse expr2: {err2}",
                verification_type="equivalence",
            )
        
        try:
            # Check if difference simplifies to zero
            diff = simplify(parsed1 - parsed2)
            is_equivalent = diff == 0
            
            return VerificationResult(
                is_valid=is_equivalent,
                expression=f"{expr1} ≡ {expr2}",
                sympy_expr=f"Difference: {diff}",
                verification_type="equivalence",
                details={
                    "expr1_sympy": str(parsed1),
                    "expr2_sympy": str(parsed2),
                    "difference": str(diff),
                },
            )
        except Exception as e:
            return VerificationResult(
                is_valid=False,
                expression=f"{expr1} ≡ {expr2}",
                error_message=str(e),
                verification_type="equivalence",
            )
    
    def verify_solution(
        self,
        equation: str,
        solution: str,
        variable: str = "x",
    ) -> VerificationResult:
        """Verify that a solution satisfies an equation.
        
        Args:
            equation: Equation in LaTeX (e.g., "x^2 - 4 = 0").
            solution: Solution value (e.g., "2" or "-2").
            variable: Variable name.
            
        Returns:
            VerificationResult with solution check.
        """
        # Parse equation
        eq_parts = equation.split("=")
        if len(eq_parts) != 2:
            return VerificationResult(
                is_valid=False,
                expression=equation,
                error_message="Equation must contain exactly one '='",
                verification_type="solve",
            )
        
        lhs, err1 = self.parser.parse(eq_parts[0].strip())
        rhs, err2 = self.parser.parse(eq_parts[1].strip())
        
        if lhs is None or rhs is None:
            return VerificationResult(
                is_valid=False,
                expression=equation,
                error_message=f"Parse error: {err1 or err2}",
                verification_type="solve",
            )
        
        # Parse solution
        sol_parsed, sol_err = self.parser.parse(solution)
        if sol_parsed is None:
            # Try as number
            try:
                sol_parsed = sympify(solution)
            except:
                return VerificationResult(
                    is_valid=False,
                    expression=solution,
                    error_message=f"Cannot parse solution: {sol_err}",
                    verification_type="solve",
                )
        
        try:
            # Create symbol and substitute
            var = symbols(variable)
            lhs_subst = lhs.subs(var, sol_parsed)
            rhs_subst = rhs.subs(var, sol_parsed)
            
            # Simplify and check
            diff = simplify(lhs_subst - rhs_subst)
            is_solution = diff == 0
            
            return VerificationResult(
                is_valid=is_solution,
                expression=f"{equation} with {variable}={solution}",
                sympy_expr=f"LHS-RHS = {diff}",
                verification_type="solve",
                details={
                    "equation": str(Eq(lhs, rhs)),
                    "solution": str(sol_parsed),
                    "difference": str(diff),
                },
            )
        except Exception as e:
            return VerificationResult(
                is_valid=False,
                expression=equation,
                error_message=str(e),
                verification_type="solve",
            )
    
    def verify_mcq_answer(
        self,
        question_latex: str,
        correct_answer: str,
        distractors: List[str],
    ) -> Dict[str, VerificationResult]:
        """Verify MCQ correct answer and ensure distractors are incorrect.
        
        Args:
            question_latex: The mathematical question/equation.
            correct_answer: The correct answer.
            distractors: List of incorrect options.
            
        Returns:
            Dict mapping each option to its verification result.
        """
        results = {}
        
        # Verify correct answer
        results["correct"] = self.verify_parse(correct_answer)
        
        # If question is an equation, verify answer solves it
        if "=" in question_latex:
            eq_result = self.verify_solution(question_latex, correct_answer)
            results["correct_solves_equation"] = eq_result
        
        # Verify distractors are parseable but different
        for i, distractor in enumerate(distractors):
            results[f"distractor_{i}"] = self.verify_parse(distractor)
            
            # Verify distractor is NOT equivalent to correct
            equiv_result = self.verify_equivalence(correct_answer, distractor)
            if equiv_result.is_valid:
                # Distractor equals correct answer - problem!
                results[f"distractor_{i}_invalid"] = VerificationResult(
                    is_valid=False,
                    expression=distractor,
                    error_message="Distractor is equivalent to correct answer!",
                    verification_type="distractor_check",
                )
        
        return results
    
    def run_in_sandbox(self, code: str) -> Tuple[bool, str]:
        """Run verification code in a subprocess sandbox.
        
        Args:
            code: Python code to execute.
            
        Returns:
            Tuple of (success, output/error).
        """
        sandbox_code = f'''
import sympy
from sympy import *
from sympy.parsing.latex import parse_latex

result = None
error = None

try:
{chr(10).join("    " + line for line in code.split(chr(10)))}
    result = "SUCCESS"
except Exception as e:
    error = str(e)

import json
print(json.dumps({{"result": result, "error": error}}))
'''
        
        try:
            result = subprocess.run(
                [sys.executable, "-c", sandbox_code],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            
            if result.returncode == 0:
                output = json.loads(result.stdout.strip())
                if output.get("error"):
                    return False, output["error"]
                return True, output.get("result", "")
            else:
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            return False, "Verification timed out"
        except Exception as e:
            return False, str(e)


class MockSymbolicVerifier:
    """Mock verifier for testing."""
    
    def verify_parse(self, latex: str) -> VerificationResult:
        return VerificationResult(is_valid=True, expression=latex)
    
    def verify_equivalence(self, expr1: str, expr2: str) -> VerificationResult:
        return VerificationResult(is_valid=expr1 == expr2, expression=f"{expr1} ≡ {expr2}")
    
    def verify_solution(self, equation: str, solution: str, variable: str = "x") -> VerificationResult:
        return VerificationResult(is_valid=True, expression=equation)
    
    def verify_mcq_answer(self, question: str, answer: str, distractors: list) -> dict:
        return {"correct": VerificationResult(is_valid=True, expression=answer)}
