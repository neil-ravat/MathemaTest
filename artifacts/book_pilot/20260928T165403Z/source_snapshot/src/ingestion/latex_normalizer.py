"""
LaTeX normalization for SymPy compatibility.

This module provides a normalization layer that standardizes LaTeX strings
before they are passed to latex2sympy2 for conversion to SymPy expressions.
Addresses the "LaTeX-to-SymPy Bridge is Brittle" concern from notes.md.
"""

from __future__ import annotations

import re
import logging
from typing import Optional

from src.models.schemas import NormalizedLatex, ValidationResult
from src.ingestion.ocr_utils import OCRValidator


logger = logging.getLogger(__name__)


class LaTeXNormalizer:
    """Normalizes LaTeX strings for SymPy processing.
    
    Implements a normalization layer that standardizes LaTeX syntax
    to improve compatibility with latex2sympy2 parser. Handles:
    - Brace balancing and correction
    - Fraction syntax standardization
    - Subscript/superscript grouping
    - Greek letter normalization
    - Environment stripping
    
    Example:
        >>> normalizer = LaTeXNormalizer()
        >>> result = normalizer.normalize(r"x_12 + \\frac12")
        >>> print(result.normalized)
        x_{12} + \\frac{1}{2}
    """
    
    # Fraction patterns that need standardization
    # \frac12 -> \frac{1}{2}
    FRAC_SHORTHAND = re.compile(r"\\frac\s*([0-9a-zA-Z])\s*([0-9a-zA-Z])")
    
    # Patterns for bare subscripts/superscripts that need braces
    # Match 2+ digits or 2+ letters (no upper limit) that aren't followed by } or more alphanumerics
    BARE_SUBSCRIPT = re.compile(r"_([0-9]{2,}|[a-zA-Z]{2,})(?![}a-zA-Z0-9])")
    BARE_SUPERSCRIPT = re.compile(r"\^([0-9]{2,}|[a-zA-Z]{2,})(?![}a-zA-Z0-9])")
    
    # Environment patterns to strip for SymPy
    ENVIRONMENT_PATTERN = re.compile(
        r"\\begin\{(equation|align|gather|multline)\*?\}|"
        r"\\end\{(equation|align|gather|multline)\*?\}"
    )
    
    # Display math delimiters to strip
    DISPLAY_MATH = re.compile(r"\$\$|\\\[|\\\]|\\displaystyle\s*")
    
    # Common LaTeX to SymPy-compatible substitutions
    SUBSTITUTIONS = [
        # Spacing commands that should be removed
        (r"\\,", " "),
        (r"\\;", " "),
        (r"\\:", " "),
        (r"\\!", ""),
        (r"\\ ", " "),
        (r"\\quad\s*", " "),
        (r"\\qquad\s*", " "),
        # Text mode in math (extract content)
        (r"\\text\{([^}]*)\}", r"\1"),
        (r"\\mathrm\{([^}]*)\}", r"\1"),
        (r"\\mathit\{([^}]*)\}", r"\1"),
        # Limits notation
        (r"\\limits", ""),
        (r"\\nolimits", ""),
        # Punctuation that might appear
        (r"\.\s*$", ""),
        (r",\s*$", ""),
    ]
    
    # Greek letters that latex2sympy2 handles well
    GREEK_LETTERS = {
        "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta",
        "iota", "kappa", "lambda", "mu", "nu", "xi", "pi", "rho", "sigma",
        "tau", "upsilon", "phi", "chi", "psi", "omega",
        "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma", "Upsilon",
        "Phi", "Psi", "Omega",
    }
    
    def __init__(
        self,
        validator: Optional[OCRValidator] = None,
        auto_fix_braces: bool = True,
        strip_environments: bool = True,
    ):
        """Initialize the LaTeX normalizer.
        
        Args:
            validator: OCRValidator instance. Creates new one if None.
            auto_fix_braces: Attempt to fix unbalanced braces.
            strip_environments: Remove LaTeX environments for SymPy.
        """
        self.validator = validator or OCRValidator(strict_mode=False)
        self.auto_fix_braces = auto_fix_braces
        self.strip_environments = strip_environments
    
    def normalize(self, latex_str: str) -> NormalizedLatex:
        """Normalize a LaTeX string for SymPy processing.
        
        Applies a series of transformations to standardize the LaTeX
        syntax and improve compatibility with latex2sympy2.
        
        Args:
            latex_str: The raw LaTeX string.
            
        Returns:
            NormalizedLatex with raw and normalized versions plus metadata.
        """
        if not latex_str:
            return NormalizedLatex(
                raw="",
                normalized="",
                sympy_compatible=True,
                validation=ValidationResult(is_valid=True, errors=[], warnings=[]),
                normalization_applied=[],
            )
        
        # Track applied normalizations
        applied: list[str] = []
        normalized = latex_str.strip()
        
        # Step 1: Strip display math delimiters
        if self.DISPLAY_MATH.search(normalized):
            normalized = self.DISPLAY_MATH.sub("", normalized)
            applied.append("stripped_display_math")
        
        # Step 2: Strip environments
        if self.strip_environments and self.ENVIRONMENT_PATTERN.search(normalized):
            normalized = self.ENVIRONMENT_PATTERN.sub("", normalized)
            applied.append("stripped_environments")
        
        # Step 3: Apply substitutions
        for pattern, replacement in self.SUBSTITUTIONS:
            if re.search(pattern, normalized):
                normalized = re.sub(pattern, replacement, normalized)
                applied.append(f"substitution_{pattern[:10]}")
        
        # Step 4: Fix fraction shorthand
        frac_match = self.FRAC_SHORTHAND.search(normalized)
        if frac_match:
            normalized = self.FRAC_SHORTHAND.sub(r"\\frac{\1}{\2}", normalized)
            applied.append("fixed_frac_shorthand")
        
        # Step 5: Add braces to bare subscripts
        if self.BARE_SUBSCRIPT.search(normalized):
            normalized = self.BARE_SUBSCRIPT.sub(r"_{\1}", normalized)
            applied.append("braced_subscripts")
        
        # Step 6: Add braces to bare superscripts
        if self.BARE_SUPERSCRIPT.search(normalized):
            normalized = self.BARE_SUPERSCRIPT.sub(r"^{\1}", normalized)
            applied.append("braced_superscripts")
        
        # Step 7: Fix unbalanced braces if enabled
        if self.auto_fix_braces:
            fixed, did_fix = self._balance_braces(normalized)
            if did_fix:
                normalized = fixed
                applied.append("balanced_braces")
        
        # Step 8: Clean up whitespace
        normalized = self._clean_whitespace(normalized)
        if normalized != latex_str.strip():
            applied.append("cleaned_whitespace")
        
        # Validate the normalized result
        validation = self.validator.validate(normalized)
        
        # Determine SymPy compatibility
        sympy_compatible = self._check_sympy_compatibility(normalized, validation)
        
        return NormalizedLatex(
            raw=latex_str,
            normalized=normalized,
            sympy_compatible=sympy_compatible,
            validation=validation,
            normalization_applied=list(set(applied)),  # Remove duplicates
        )
    
    def _balance_braces(self, latex_str: str) -> tuple[str, bool]:
        """Attempt to balance unmatched braces and parentheses.
        
        Args:
            latex_str: The LaTeX string to fix.
            
        Returns:
            Tuple of (fixed_string, was_modified).
        """
        result = latex_str
        modified = False
        
        # Balance curly braces
        cleaned_braces = re.sub(r"\\[{}]", "", result)
        open_braces = cleaned_braces.count("{")
        close_braces = cleaned_braces.count("}")
        
        if open_braces > close_braces:
            result = result + ("}" * (open_braces - close_braces))
            modified = True
            logger.warning(f"Added {open_braces - close_braces} closing brace(s)")
        elif close_braces > open_braces:
            result = ("{" * (close_braces - open_braces)) + result
            modified = True
            logger.warning(f"Added {close_braces - open_braces} opening brace(s)")
        
        # Balance parentheses (common in math expressions)
        cleaned_parens = re.sub(r"\\\\\\(|\\\\\\)", "", result)
        open_parens = cleaned_parens.count("(")
        close_parens = cleaned_parens.count(")")
        
        if open_parens > close_parens:
            result = result + (")" * (open_parens - close_parens))
            modified = True
            logger.warning(f"Added {open_parens - close_parens} closing parenthesis(es)")
        elif close_parens > open_parens:
            result = ("(" * (close_parens - open_parens)) + result
            modified = True
            logger.warning(f"Added {close_parens - open_parens} opening parenthesis(es)")
        
        # Balance square brackets
        cleaned_brackets = re.sub(r"\\[\[\]]", "", result)
        open_brackets = cleaned_brackets.count("[")
        close_brackets = cleaned_brackets.count("]")
        
        if open_brackets > close_brackets:
            result = result + ("]" * (open_brackets - close_brackets))
            modified = True
            logger.warning(f"Added {open_brackets - close_brackets} closing bracket(s)")
        elif close_brackets > open_brackets:
            result = ("[" * (close_brackets - open_brackets)) + result
            modified = True
            logger.warning(f"Added {close_brackets - open_brackets} opening bracket(s)")
        
        return result, modified
    
    def _clean_whitespace(self, latex_str: str) -> str:
        """Clean up excessive whitespace.
        
        Args:
            latex_str: The LaTeX string to clean.
            
        Returns:
            Cleaned string with normalized whitespace.
        """
        # Collapse multiple spaces
        result = re.sub(r" {2,}", " ", latex_str)
        
        # Only remove spaces immediately inside braces (not around them)
        # This preserves operator spacing like "x + y"
        result = re.sub(r"{\s+", "{", result)
        result = re.sub(r"\s+}", "}", result)
        
        # Remove leading/trailing whitespace
        return result.strip()
    
    def _check_sympy_compatibility(
        self,
        normalized: str,
        validation: ValidationResult,
    ) -> bool:
        """Check if normalized LaTeX is likely SymPy compatible.
        
        Args:
            normalized: The normalized LaTeX string.
            validation: Validation result from OCR validator.
            
        Returns:
            True if the LaTeX should parse with latex2sympy2.
        """
        # Must pass validation
        if not validation.is_valid:
            return False
        
        # Check for known problematic patterns
        problematic_patterns = [
            r"\\begin\{",  # Environments not stripped
            r"\\end\{",
            r"\\[a-zA-Z]+\[",  # Commands with square bracket args
            r"&&",  # Alignment markers
            r"\\\\",  # Line breaks
        ]
        
        for pattern in problematic_patterns:
            if re.search(pattern, normalized):
                return False
        
        # If it's simple enough and validated, assume compatible
        return True
    
    def normalize_batch(self, latex_strings: list[str]) -> list[NormalizedLatex]:
        """Normalize multiple LaTeX strings.
        
        Args:
            latex_strings: List of LaTeX strings to normalize.
            
        Returns:
            List of NormalizedLatex objects in same order.
        """
        return [self.normalize(s) for s in latex_strings]
    
    def extract_variables(self, latex_str: str) -> list[str]:
        """Extract variable symbols from LaTeX expression.
        
        Args:
            latex_str: The LaTeX string to analyze.
            
        Returns:
            List of detected variable symbols.
        """
        variables: set[str] = set()
        
        # Remove commands
        cleaned = re.sub(r"\\[a-zA-Z]+", " ", latex_str)
        
        # Remove numbers, operators, and braces
        cleaned = re.sub(r"[0-9{}()\[\]+\-*/=<>^_,.]", " ", cleaned)
        
        # Extract single letters
        letters = re.findall(r"\b([a-zA-Z])\b", cleaned)
        
        # Filter out common non-variable letters
        non_variables = {"d", "D", "e", "i", "E", "I"}  # Differential, euler, imaginary
        
        for letter in letters:
            if letter not in non_variables:
                variables.add(letter)
        
        return sorted(list(variables))
    
    def extract_functions(self, latex_str: str) -> list[str]:
        """Extract function names from LaTeX expression.
        
        Args:
            latex_str: The LaTeX string to analyze.
            
        Returns:
            List of detected function names.
        """
        functions: set[str] = set()
        
        # Common mathematical functions
        function_commands = [
            "sin", "cos", "tan", "cot", "sec", "csc",
            "arcsin", "arccos", "arctan",
            "sinh", "cosh", "tanh", "coth",
            "log", "ln", "exp", "sqrt",
            "lim", "sum", "prod", "int",
        ]
        
        for func in function_commands:
            if f"\\{func}" in latex_str:
                functions.add(func)
        
        return sorted(list(functions))
