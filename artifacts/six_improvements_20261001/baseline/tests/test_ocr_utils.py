"""
Unit tests for OCR validation utilities.

Tests the OCRValidator class for:
- Bracket matching
- Subscript/superscript validation
- Suspicious pattern detection
- Hallucination detection
"""

import pytest
from src.ingestion.ocr_utils import OCRValidator
from src.models.schemas import ValidationResult


@pytest.fixture
def validator():
    """Create OCRValidator in default strict mode."""
    return OCRValidator(strict_mode=True)


@pytest.fixture
def lenient_validator():
    """Create OCRValidator in lenient mode."""
    return OCRValidator(strict_mode=False)


class TestBracketMatching:
    """Tests for bracket/brace matching validation."""
    
    def test_balanced_braces_valid(self, validator):
        """Balanced braces should pass validation."""
        latex = r"\frac{1}{2}"
        result = validator.validate(latex)
        assert result.is_valid is True
        assert len(result.errors) == 0
    
    def test_balanced_nested_braces(self, validator):
        """Nested balanced braces should pass validation."""
        latex = r"\frac{\frac{1}{2}}{3}"
        result = validator.validate(latex)
        assert result.is_valid is True
    
    def test_missing_closing_brace(self, validator):
        """Missing closing brace should fail validation."""
        latex = r"\frac{1}{2"
        result = validator.validate(latex)
        assert result.is_valid is False
        assert any(e.error_type == "unclosed_bracket" for e in result.errors)
    
    def test_missing_opening_brace(self, validator):
        """Missing opening brace should fail validation."""
        latex = r"\frac{1}2}"
        result = validator.validate(latex)
        assert result.is_valid is False
        assert any(e.error_type == "unmatched_bracket" for e in result.errors)
    
    def test_mismatched_brackets(self, validator):
        """Mismatched bracket types should fail validation."""
        latex = r"\frac{1}{2]"
        result = validator.validate(latex)
        assert result.is_valid is False
        assert any(e.error_type == "mismatched_bracket" for e in result.errors)
    
    def test_balanced_parentheses(self, validator):
        """Balanced parentheses should pass validation."""
        latex = r"(x + y) \cdot (a + b)"
        result = validator.validate(latex)
        assert result.is_valid is True
    
    def test_balanced_square_brackets(self, validator):
        """Balanced square brackets should pass validation."""
        latex = r"[a, b] \cup [c, d]"
        result = validator.validate(latex)
        assert result.is_valid is True
    
    def test_escaped_braces_ignored(self, validator):
        """Escaped braces should not affect bracket matching."""
        latex = r"\{1, 2, 3\}"
        result = validator.validate(latex)
        assert result.is_valid is True


class TestSubscriptValidation:
    """Tests for subscript/superscript validation."""
    
    def test_single_char_subscript_valid(self, validator):
        """Single character subscripts should pass validation."""
        latex = r"x_n + y_m"
        result = validator.validate(latex)
        assert result.is_valid is True
    
    def test_braced_subscript_valid(self, validator):
        """Braced subscripts should pass validation."""
        latex = r"x_{12} + y_{n+1}"
        result = validator.validate(latex)
        assert result.is_valid is True
    
    def test_multi_char_subscript_without_braces(self, validator):
        """Multi-char subscript without braces should fail validation."""
        latex = r"x_12"
        result = validator.validate(latex)
        assert result.is_valid is False
        assert any("subscript" in e.error_type for e in result.errors)
    
    def test_multi_char_superscript_without_braces(self, validator):
        """Multi-char superscript without braces should fail validation."""
        latex = r"x^10"
        result = validator.validate(latex)
        assert result.is_valid is False
        assert any("superscript" in e.error_type for e in result.errors)
    
    def test_single_digit_subscript_valid(self, validator):
        """Single digit subscripts are valid without braces."""
        latex = r"x_1 + x_2 + x_3"
        result = validator.validate(latex)
        assert result.is_valid is True


class TestSuspiciousPatterns:
    """Tests for suspicious pattern detection."""
    
    def test_multiple_operators_flagged(self, validator):
        """Multiple consecutive operators should be flagged."""
        latex = r"x +++ y"
        result = validator.validate(latex)
        assert result.is_valid is False
        assert any("suspicious_pattern" in e.error_type for e in result.errors)
    
    def test_empty_braces_flagged(self, validator):
        """Empty brace groups should be flagged."""
        latex = r"x + {} + y"
        result = validator.validate(latex)
        assert result.is_valid is False
        assert any("suspicious_pattern" in e.error_type for e in result.errors)
    
    def test_consecutive_subscript_markers_flagged(self, validator):
        """Consecutive subscript markers should be flagged."""
        latex = r"x__y"
        result = validator.validate(latex)
        assert result.is_valid is False
    
    def test_backslash_digit_flagged(self, validator):
        """Backslash followed by digit should be flagged."""
        latex = r"\1 + x"
        result = validator.validate(latex)
        assert result.is_valid is False
    
    def test_normal_operators_valid(self, validator):
        """Normal single operators should pass."""
        latex = r"x + y - z * w / v"
        result = validator.validate(latex)
        assert result.is_valid is True


class TestCommandValidation:
    """Tests for LaTeX command validation."""
    
    def test_known_commands_valid(self, validator):
        """Known LaTeX commands should not generate warnings."""
        latex = r"\frac{1}{2} + \sqrt{x} + \sin(\theta)"
        result = validator.validate(latex)
        assert result.is_valid is True
        # Should not have warnings about frac, sqrt, sin, theta
        command_warnings = [w for w in result.warnings if "command" in w.error_type]
        assert len(command_warnings) == 0
    
    def test_unknown_commands_warned(self, lenient_validator):
        """Unknown commands should generate warnings (not errors in lenient mode)."""
        latex = r"\unknowncommand{x}"
        result = lenient_validator.validate(latex)
        # In lenient mode, unknown commands are warnings not errors
        assert any("unknown_command" in w.error_type for w in result.warnings)
    
    def test_greek_letters_valid(self, validator):
        """Greek letter commands should be valid."""
        latex = r"\alpha + \beta + \gamma + \Gamma"
        result = validator.validate(latex)
        assert result.is_valid is True


class TestConfidenceScoring:
    """Tests for validation confidence scores."""
    
    def test_perfect_latex_high_confidence(self, validator):
        """Valid LaTeX should have high confidence."""
        latex = r"\frac{1}{2}"
        result = validator.validate(latex)
        assert result.confidence_score >= 0.9
    
    def test_errors_lower_confidence(self, validator):
        """Errors should lower confidence score."""
        latex = r"\frac{1}{2"  # Missing brace
        result = validator.validate(latex)
        assert result.confidence_score < 1.0
    
    def test_empty_string_high_confidence(self, validator):
        """Empty string should have max confidence."""
        result = validator.validate("")
        assert result.confidence_score == 1.0


class TestContextExtraction:
    """Tests for error context extraction."""
    
    def test_error_includes_context(self, validator):
        """Errors should include surrounding context."""
        latex = r"very long expression with \frac{1}{2 missing brace here"
        result = validator.validate(latex)
        assert len(result.errors) > 0
        # At least one error should have context
        assert any(e.context is not None for e in result.errors)
    
    def test_error_includes_position(self, validator):
        """Errors should include character position."""
        latex = r"\frac{1}{2"
        result = validator.validate(latex)
        assert len(result.errors) > 0
        assert all(e.position is not None for e in result.errors)


class TestBatchValidation:
    """Tests for batch validation."""
    
    def test_batch_processes_all(self, validator):
        """Batch should validate all inputs."""
        inputs = [
            r"\frac{1}{2}",  # Valid
            r"\frac{1}{2",   # Invalid
            r"x^{2}",        # Valid
        ]
        results = validator.validate_batch(inputs)
        
        assert len(results) == 3
        assert results[0].is_valid is True
        assert results[1].is_valid is False
        assert results[2].is_valid is True


class TestEdgeCases:
    """Tests for edge cases."""
    
    def test_none_like_empty(self, validator):
        """None-like values should not crash."""
        result = validator.validate("")
        assert result.is_valid is True
    
    def test_whitespace_only(self, validator):
        """Whitespace-only input should be valid."""
        result = validator.validate("   ")
        assert result.is_valid is True
    
    def test_very_long_input(self, validator):
        """Very long valid input should pass."""
        latex = r"\frac{1}{2} + " * 100
        latex = latex.rstrip(" + ")
        result = validator.validate(latex)
        assert result.is_valid is True
    
    def test_unicode_in_latex(self, validator):
        """Unicode characters should not crash validation."""
        latex = r"\frac{α}{β}"  # Using actual Greek letters
        result = validator.validate(latex)
        # Should complete without error
        assert isinstance(result, ValidationResult)
