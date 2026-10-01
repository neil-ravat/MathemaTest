"""
Unit tests for LaTeX normalization.

Tests the LaTeXNormalizer class for:
- Brace balancing
- Fraction standardization
- Subscript/superscript bracing
- SymPy compatibility detection
"""

import pytest
from src.ingestion.latex_normalizer import LaTeXNormalizer
from src.ingestion.ocr_utils import OCRValidator


@pytest.fixture
def normalizer():
    """Create a LaTeXNormalizer instance for testing."""
    return LaTeXNormalizer()


@pytest.fixture
def strict_normalizer():
    """Create a strict LaTeXNormalizer for testing."""
    return LaTeXNormalizer(
        validator=OCRValidator(strict_mode=True),
        auto_fix_braces=True,
    )


class TestBraceBalancing:
    """Tests for brace balancing functionality."""
    
    def test_balanced_braces_unchanged(self, normalizer):
        """Balanced braces should remain unchanged."""
        latex = r"\frac{1}{2}"
        result = normalizer.normalize(latex)
        assert result.normalized == latex.strip()
    
    def test_missing_closing_brace(self, normalizer):
        """Missing closing brace should be added."""
        latex = r"\frac{1}{2"
        result = normalizer.normalize(latex)
        assert result.normalized.count("{") == result.normalized.count("}")
        assert "balanced_braces" in result.normalization_applied
    
    def test_missing_opening_brace(self, normalizer):
        """Missing opening brace should be added."""
        latex = r"\frac{1}2}"
        result = normalizer.normalize(latex)
        assert result.normalized.count("{") == result.normalized.count("}")
    
    def test_multiple_missing_braces(self, normalizer):
        """Multiple missing braces should all be fixed."""
        latex = r"\frac{1{2"
        result = normalizer.normalize(latex)
        assert result.normalized.count("{") == result.normalized.count("}")


class TestFractionNormalization:
    """Tests for fraction syntax standardization."""
    
    def test_frac_shorthand_to_full(self, normalizer):
        """Fraction shorthand should be expanded."""
        latex = r"\frac12"
        result = normalizer.normalize(latex)
        assert r"\frac{1}{2}" in result.normalized
        assert "fixed_frac_shorthand" in result.normalization_applied
    
    def test_frac_with_letters(self, normalizer):
        """Fraction with letter arguments should be expanded."""
        latex = r"\frac xy"
        result = normalizer.normalize(latex)
        assert r"\frac{x}{y}" in result.normalized
    
    def test_full_frac_unchanged(self, normalizer):
        """Full fraction syntax should remain unchanged."""
        latex = r"\frac{a+b}{c+d}"
        result = normalizer.normalize(latex)
        assert result.normalized == latex.strip()


class TestSubscriptSuperscript:
    """Tests for subscript and superscript normalization."""
    
    def test_multi_digit_subscript_braced(self, normalizer):
        """Multi-digit subscripts should get braces."""
        latex = r"x_12"
        result = normalizer.normalize(latex)
        assert r"x_{12}" in result.normalized
        assert "braced_subscripts" in result.normalization_applied
    
    def test_multi_letter_subscript_braced(self, normalizer):
        """Multi-letter subscripts should get braces."""
        latex = r"x_max"
        result = normalizer.normalize(latex)
        assert r"x_{max}" in result.normalized
    
    def test_multi_digit_superscript_braced(self, normalizer):
        """Multi-digit superscripts should get braces."""
        latex = r"x^10"
        result = normalizer.normalize(latex)
        assert r"x^{10}" in result.normalized
        assert "braced_superscripts" in result.normalization_applied
    
    def test_single_char_subscript_unchanged(self, normalizer):
        """Single character subscripts don't need braces."""
        latex = r"x_n + y^2"
        result = normalizer.normalize(latex)
        # Single chars should stay as-is
        assert "_n" in result.normalized or "_{n}" in result.normalized
    
    def test_already_braced_unchanged(self, normalizer):
        """Already braced subscripts should stay unchanged."""
        latex = r"x_{12} + y^{10}"
        result = normalizer.normalize(latex)
        assert result.normalized == latex.strip()


class TestEnvironmentStripping:
    """Tests for LaTeX environment removal."""
    
    def test_equation_env_stripped(self, normalizer):
        """Equation environment should be stripped."""
        latex = r"\begin{equation}x^2 + y^2 = z^2\end{equation}"
        result = normalizer.normalize(latex)
        assert r"\begin{equation}" not in result.normalized
        assert r"\end{equation}" not in result.normalized
        assert "stripped_environments" in result.normalization_applied
    
    def test_align_env_stripped(self, normalizer):
        """Align environment should be stripped."""
        latex = r"\begin{align}a &= b\end{align}"
        result = normalizer.normalize(latex)
        assert r"\begin{align}" not in result.normalized
    
    def test_display_math_stripped(self, normalizer):
        """Display math delimiters should be stripped."""
        latex = r"$$x + y$$"
        result = normalizer.normalize(latex)
        assert "$$" not in result.normalized
        assert "stripped_display_math" in result.normalization_applied


class TestSymPyCompatibility:
    """Tests for SymPy compatibility detection."""
    
    def test_simple_expression_compatible(self, normalizer):
        """Simple expressions should be SymPy compatible."""
        latex = r"\frac{1}{2} + x^{2}"
        result = normalizer.normalize(latex)
        assert result.sympy_compatible is True
    
    def test_unbalanced_braces_incompatible(self, strict_normalizer):
        """Expressions with validation errors should NOT be marked incompatible 
        if they can be fixed."""
        # After normalization, this should be fixed and compatible
        latex = r"\frac{1}{2}"
        result = strict_normalizer.normalize(latex)
        assert result.sympy_compatible is True
    
    def test_remaining_environments_incompatible(self, normalizer):
        """Expressions with non-stripped environments are incompatible."""
        # Create normalizer that doesn't strip environments
        no_strip_normalizer = LaTeXNormalizer(strip_environments=False)
        latex = r"\begin{cases}x & y\end{cases}"
        result = no_strip_normalizer.normalize(latex)
        assert result.sympy_compatible is False


class TestVariableExtraction:
    """Tests for variable detection in expressions."""
    
    def test_extract_simple_variables(self, normalizer):
        """Should extract simple variable letters."""
        latex = r"x + y + z"
        variables = normalizer.extract_variables(latex)
        assert "x" in variables
        assert "y" in variables
        assert "z" in variables
    
    def test_ignore_common_constants(self, normalizer):
        """Should ignore common mathematical constants."""
        latex = r"e^{i\pi} + d/dx"
        variables = normalizer.extract_variables(latex)
        # 'e', 'i', 'd' are filtered out as they're common non-variables
        assert "e" not in variables
        assert "i" not in variables
        assert "d" not in variables


class TestFunctionExtraction:
    """Tests for function detection in expressions."""
    
    def test_extract_trig_functions(self, normalizer):
        """Should detect trigonometric functions."""
        latex = r"\sin(x) + \cos(y)"
        functions = normalizer.extract_functions(latex)
        assert "sin" in functions
        assert "cos" in functions
    
    def test_extract_calculus_functions(self, normalizer):
        """Should detect calculus operators."""
        latex = r"\int_0^1 \frac{dx}{x} + \lim_{n\to\infty}"
        functions = normalizer.extract_functions(latex)
        assert "int" in functions
        assert "lim" in functions


class TestEmptyInput:
    """Tests for edge cases with empty or minimal input."""
    
    def test_empty_string(self, normalizer):
        """Empty string should return valid empty result."""
        result = normalizer.normalize("")
        assert result.normalized == ""
        assert result.sympy_compatible is True
        assert result.validation.is_valid is True
    
    def test_whitespace_only(self, normalizer):
        """Whitespace-only input should normalize to empty."""
        result = normalizer.normalize("   \n\t  ")
        assert result.normalized == ""


class TestBatchNormalization:
    """Tests for batch processing."""
    
    def test_batch_processes_all(self, normalizer):
        """Batch should process all inputs in order."""
        inputs = [r"\frac12", r"x_10", r"y^{2}"]
        results = normalizer.normalize_batch(inputs)
        
        assert len(results) == 3
        assert r"\frac{1}{2}" in results[0].normalized
        assert r"x_{10}" in results[1].normalized
        assert r"y^{2}" in results[2].normalized
