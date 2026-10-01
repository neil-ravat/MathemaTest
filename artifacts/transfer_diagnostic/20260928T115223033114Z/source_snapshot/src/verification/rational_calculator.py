"""Bounded exact arithmetic; generated Lean checks arithmetic, not source fidelity."""
import ast
import re
from fractions import Fraction


_NUMBER = r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)"
_CLAIM = re.compile(rf"[+-]?{_NUMBER}(?:\s*/\s*[+-]?{_NUMBER})?\Z")
_LIMIT = 10**12


def _bounded(value):
    if abs(value.numerator) > _LIMIT or value.denominator > _LIMIT:
        raise ValueError("Numerator or denominator exceeds 10^12")
    return value


def _parse(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 2000:
        raise ValueError("Arithmetic text must contain 1 to 2000 characters")
    text = text.strip()
    try:
        tree = ast.parse(text, mode="eval")
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise ValueError("Invalid arithmetic syntax") from exc
    if sum(1 for _ in ast.walk(tree)) > 256:
        raise ValueError("Expression exceeds 256 AST nodes")

    def visit(node):
        # Return exact value and symbolic integer numerator/denominator trees.
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            literal = ast.get_source_segment(text, node)
            if not re.fullmatch(_NUMBER, literal):
                raise ValueError("Only ordinary integer and decimal literals are allowed")
            value = _bounded(Fraction(literal))  # Never construct from a binary float.
            return value, f"({value.numerator} : Int)", f"({value.denominator} : Int)"
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value, numerator, denominator = visit(node.operand)
            if isinstance(node.op, ast.USub):
                return -value, f"(-{numerator})", denominator
            return value, numerator, denominator
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            left, ln, ld = visit(node.left)
            right, rn, rd = visit(node.right)
            if isinstance(node.op, ast.Add):
                value, n, d = left + right, f"(({ln} * {rd}) + ({rn} * {ld}))", f"({ld} * {rd})"
            elif isinstance(node.op, ast.Sub):
                value, n, d = left - right, f"(({ln} * {rd}) - ({rn} * {ld}))", f"({ld} * {rd})"
            elif isinstance(node.op, ast.Mult):
                value, n, d = left * right, f"({ln} * {rn})", f"({ld} * {rd})"
            else:
                if not right:
                    raise ValueError("Division by zero")
                value, n, d = left / right, f"({ln} * {rd})", f"({ld} * {rn})"
            return _bounded(value), n, d
        raise ValueError("Only numbers, parentheses, unary signs and + - * / are allowed")

    try:
        return visit(tree.body)
    except RecursionError as exc:
        raise ValueError("Arithmetic nesting is too deep") from exc


def check_calculation(expression: str, claimed_value: str) -> dict:
    """Check exact equality, raising ValueError on unsupported or unsafe input.

    The Lean proposition retains arithmetic from the input expression rather
    than asserting an equality of precomputed results. Denominator nonzero
    checks happen here, not in Lean; the Lean theorem certifies only the
    resulting integer cross multiplication, never units or textbook claims.
    """
    value, numerator, denominator = _parse(expression)
    if not isinstance(claimed_value, str) or len(claimed_value) > 2000 or not _CLAIM.fullmatch(claimed_value.strip()):
        raise ValueError("Claim must be a signed integer, decimal, or numeric fraction")
    claim, cn, cd = _parse(claimed_value)
    lean_code = (
        "-- Arithmetic only; nonzero divisors checked by the bounded calculator.\n"
        f"example : ({numerator} * {cd}) = ({cn} * {denominator}) := by decide\n"
    )
    return {"exact_result": str(value), "consistent": value == claim, "lean_code": lean_code}
