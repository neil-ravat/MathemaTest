"""
OCR validation utilities for detecting LaTeX hallucinations.

This module provides strict validation to catch common OCR errors,
particularly in subscripts, superscripts, and bracket matching that
can render mathematical expressions invalid for SymPy processing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from src.models.schemas import ValidationError, ValidationResult


@dataclass
class BracketInfo:
    """Information about a bracket character in LaTeX string."""
    
    char: str
    position: int
    is_opening: bool


class OCRValidator:
    """Validator for detecting OCR hallucinations in LaTeX output.
    
    Implements strict validation rules targeting common OCR errors:
    - Mismatched brackets/braces/parentheses
    - Invalid subscript/superscript patterns
    - Malformed LaTeX commands
    - Suspicious character sequences
    
    Example:
        >>> validator = OCRValidator()
        >>> result = validator.validate(r"\\frac{1}{2}")
        >>> print(result.is_valid)
        True
        >>> result = validator.validate(r"\\frac{1}{2")
        >>> print(result.is_valid)
        False
    """
    
    # Matching bracket pairs
    BRACKET_PAIRS = {
        "{": "}",
        "(": ")",
        "[": "]",
    }
    
    # Common valid LaTeX commands (non-exhaustive, for validation hints)
    VALID_COMMANDS = {
        # Fractions and roots
        "frac", "dfrac", "tfrac", "sqrt", "root",
        # Greek letters (lowercase)
        "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta",
        "iota", "kappa", "lambda", "mu", "nu", "xi", "pi", "rho", "sigma",
        "tau", "upsilon", "phi", "chi", "psi", "omega",
        # Greek letters (uppercase)
        "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma", "Upsilon",
        "Phi", "Psi", "Omega",
        # Operations
        "sum", "prod", "int", "iint", "iiint", "oint", "lim", "log", "ln", "exp",
        "sin", "cos", "tan", "cot", "sec", "csc", "arcsin", "arccos", "arctan",
        "sinh", "cosh", "tanh", "coth",
        # Relations
        "leq", "geq", "neq", "approx", "equiv", "sim", "subset", "supset",
        "subseteq", "supseteq", "in", "notin", "ni",
        # Arrows
        "to", "rightarrow", "leftarrow", "leftrightarrow", "Rightarrow",
        "Leftarrow", "Leftrightarrow", "mapsto",
        # Accents and modifiers
        "hat", "bar", "vec", "dot", "ddot", "tilde", "overline", "underline",
        "overbrace", "underbrace",
        # Spacing and formatting
        "quad", "qquad", "text", "mathrm", "mathbf", "mathit", "mathcal",
        "mathbb", "mathfrak",
        # Delimiters
        "left", "right", "big", "Big", "bigg", "Bigg",
        # Matrices and environments
        "begin", "end", "matrix", "pmatrix", "bmatrix", "cases",
        # Miscellaneous
        "cdot", "times", "div", "pm", "mp", "infty", "partial", "nabla",
        "forall", "exists", "neg", "land", "lor", "ldots", "cdots", "vdots",
        "ddots", "prime",
    }
    
    # Patterns that commonly indicate OCR hallucinations
    SUSPICIOUS_PATTERNS = [
        # Double operators without intervening content
        (r"[+\-*/=]{3,}", "Multiple consecutive operators"),
        # Empty groups
        (r"\{\s*\}", "Empty brace group"),
        # Consecutive carets or underscores
        (r"[\^_]{2,}", "Consecutive sub/superscript markers"),
        # Backslash followed by digit (invalid command)
        (r"\\[0-9]", "Backslash followed by digit"),
        # Very long subscript without braces (likely missing brace)
        (r"_[a-zA-Z]{4,}(?![}])", "Long subscript possibly missing braces"),
    ]
    
    # Patterns for subscript/superscript validation
    SUBSCRIPT_PATTERN = re.compile(r"_(\{[^}]*\}|[a-zA-Z0-9])")
    SUPERSCRIPT_PATTERN = re.compile(r"\^(\{[^}]*\}|[a-zA-Z0-9])")
    
    def __init__(self, strict_mode: bool = True):
        """Initialize the OCR validator.
        
        Args:
            strict_mode: If True, treat warnings as errors. Defaults to True.
        """
        self.strict_mode = strict_mode
    
    def validate(self, latex_str: str) -> ValidationResult:
        """Validate a LaTeX string for OCR hallucinations.
        
        Performs comprehensive validation including:
        - Bracket/brace matching
        - Subscript/superscript syntax
        - LaTeX command validity
        - Suspicious pattern detection
        
        Args:
            latex_str: The LaTeX string to validate.
            
        Returns:
            ValidationResult with validation status and any errors/warnings.
        """
        errors: list[ValidationError] = []
        warnings: list[ValidationError] = []
        
        if not latex_str or not latex_str.strip():
            return ValidationResult(
                is_valid=True,
                errors=[],
                warnings=[],
                confidence_score=1.0,
            )
        
        # Run all validation checks
        bracket_errors = self._check_bracket_matching(latex_str)
        errors.extend(bracket_errors)
        
        subscript_errors = self._check_subscript_syntax(latex_str)
        errors.extend(subscript_errors)
        
        command_warnings = self._check_command_validity(latex_str)
        warnings.extend(command_warnings)
        
        pattern_issues = self._check_suspicious_patterns(latex_str)
        if self.strict_mode:
            errors.extend(pattern_issues)
        else:
            warnings.extend(pattern_issues)
        
        # Calculate confidence score
        total_issues = len(errors) + len(warnings) * 0.5
        confidence = max(0.0, 1.0 - (total_issues * 0.1))
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            confidence_score=round(confidence, 4),
        )
    
    def _check_bracket_matching(self, latex_str: str) -> list[ValidationError]:
        """Check for balanced brackets, braces, and parentheses.
        
        Handles LaTeX escaping (\\{, \\}) and \\left/\\right delimiters.
        
        Args:
            latex_str: The LaTeX string to check.
            
        Returns:
            List of validation errors for unmatched brackets.
        """
        errors: list[ValidationError] = []
        
        # Remove escaped brackets for matching purposes
        cleaned = re.sub(r"\\[{}()\[\]]", "X", latex_str)
        
        # Track bracket positions
        stack: list[BracketInfo] = []
        
        i = 0
        while i < len(cleaned):
            char = cleaned[i]
            
            if char in self.BRACKET_PAIRS:
                stack.append(BracketInfo(char, i, is_opening=True))
            elif char in self.BRACKET_PAIRS.values():
                # Find the expected opening bracket
                expected_open = None
                for open_b, close_b in self.BRACKET_PAIRS.items():
                    if close_b == char:
                        expected_open = open_b
                        break
                
                if not stack:
                    errors.append(ValidationError(
                        error_type="unmatched_bracket",
                        message=f"Unexpected closing '{char}' without matching opening",
                        position=i,
                        context=self._get_context(latex_str, i),
                    ))
                elif stack[-1].char != expected_open:
                    errors.append(ValidationError(
                        error_type="mismatched_bracket",
                        message=f"Closing '{char}' doesn't match opening '{stack[-1].char}'",
                        position=i,
                        context=self._get_context(latex_str, i),
                    ))
                    stack.pop()
                else:
                    stack.pop()
            
            i += 1
        
        # Report any unclosed brackets
        for bracket_info in stack:
            errors.append(ValidationError(
                error_type="unclosed_bracket",
                message=f"Unclosed '{bracket_info.char}' bracket",
                position=bracket_info.position,
                context=self._get_context(latex_str, bracket_info.position),
            ))
        
        return errors
    
    def _check_subscript_syntax(self, latex_str: str) -> list[ValidationError]:
        """Validate subscript and superscript syntax.
        
        Catches common OCR errors like:
        - x_12 instead of x_{12}
        - Nested subscripts without proper grouping
        
        Args:
            latex_str: The LaTeX string to check.
            
        Returns:
            List of validation errors for invalid subscript syntax.
        """
        errors: list[ValidationError] = []
        
        # Check for potentially problematic subscript patterns
        # Pattern: underscore followed by multiple characters not in braces
        multi_char_subscript = re.compile(r"_([a-zA-Z]{2,}|[0-9]{2,})(?![}])")
        
        for match in multi_char_subscript.finditer(latex_str):
            # Verify this isn't inside a brace group already
            content = match.group(1)
            pos = match.start()
            
            # Check if this might be a valid single-char subscript followed by text
            # by looking at what comes after
            if len(content) > 1:
                errors.append(ValidationError(
                    error_type="subscript_missing_braces",
                    message=f"Multi-character subscript '_{content}' should likely be '_{{content}}'",
                    position=pos,
                    context=self._get_context(latex_str, pos),
                ))
        
        # Same check for superscripts
        multi_char_superscript = re.compile(r"\^([a-zA-Z]{2,}|[0-9]{2,})(?![}])")
        
        for match in multi_char_superscript.finditer(latex_str):
            content = match.group(1)
            pos = match.start()
            
            if len(content) > 1:
                errors.append(ValidationError(
                    error_type="superscript_missing_braces",
                    message=f"Multi-character superscript '^{content}' should likely be '^{{{content}}}'",
                    position=pos,
                    context=self._get_context(latex_str, pos),
                ))
        
        return errors
    
    def _check_command_validity(self, latex_str: str) -> list[ValidationError]:
        """Check for potentially invalid LaTeX commands.
        
        Issues warnings for commands not in the known valid set.
        
        Args:
            latex_str: The LaTeX string to check.
            
        Returns:
            List of validation warnings for unknown commands.
        """
        warnings: list[ValidationError] = []
        
        # Extract all commands (backslash followed by letters)
        command_pattern = re.compile(r"\\([a-zA-Z]+)")
        
        for match in command_pattern.finditer(latex_str):
            cmd = match.group(1)
            if cmd not in self.VALID_COMMANDS:
                # Only warn about completely unknown commands
                # (some valid commands may not be in our list)
                if not self._is_likely_valid_command(cmd):
                    warnings.append(ValidationError(
                        error_type="unknown_command",
                        message=f"Unknown LaTeX command '\\{cmd}' - verify OCR accuracy",
                        position=match.start(),
                        context=self._get_context(latex_str, match.start()),
                    ))
        
        return warnings
    
    def _is_likely_valid_command(self, cmd: str) -> bool:
        """Check if a command is likely valid even if not in our list.
        
        Args:
            cmd: The command name (without backslash).
            
        Returns:
            True if the command seems valid.
        """
        # Commands that end with common suffixes are likely valid
        valid_suffixes = ["text", "math", "box", "space", "style", "size"]
        for suffix in valid_suffixes:
            if cmd.endswith(suffix):
                return True
        
        # Short commands (1-2 chars) are often valid spacing commands
        if len(cmd) <= 2:
            return True
        
        return False
    
    def _check_suspicious_patterns(self, latex_str: str) -> list[ValidationError]:
        """Check for patterns that commonly indicate OCR errors.
        
        Args:
            latex_str: The LaTeX string to check.
            
        Returns:
            List of validation errors for suspicious patterns.
        """
        errors: list[ValidationError] = []
        
        for pattern, description in self.SUSPICIOUS_PATTERNS:
            for match in re.finditer(pattern, latex_str):
                errors.append(ValidationError(
                    error_type="suspicious_pattern",
                    message=f"Suspicious pattern detected: {description}",
                    position=match.start(),
                    context=self._get_context(latex_str, match.start()),
                ))
        
        return errors
    
    def _get_context(self, text: str, position: int, window: int = 15) -> str:
        """Get surrounding context for error reporting.
        
        Args:
            text: The full text.
            position: The position of interest.
            window: How many characters to show on each side.
            
        Returns:
            Context string with ellipsis if truncated.
        """
        start = max(0, position - window)
        end = min(len(text), position + window)
        
        context = text[start:end]
        
        if start > 0:
            context = "..." + context
        if end < len(text):
            context = context + "..."
        
        return context
    
    def validate_batch(self, latex_strings: list[str]) -> list[ValidationResult]:
        """Validate multiple LaTeX strings.
        
        Args:
            latex_strings: List of LaTeX strings to validate.
            
        Returns:
            List of ValidationResult objects in same order as input.
        """
        return [self.validate(s) for s in latex_strings]
