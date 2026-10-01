"""Bounded SI dimensional diagnostics; never certify transcription or physics."""
import ast
import re

from src.ingestion.source_quality import quantity_symbol_mentions

# Exponents of mass, length, time, current. This registry is prior knowledge,
# not a claim that the source supplied or verified these dimensions.
DIMENSIONS = {
    'charge': (0, 0, 1, 1), 'electric charge': (0, 0, 1, 1),
    'current': (0, 0, 0, 1), 'electric current': (0, 0, 0, 1),
    'time': (0, 0, 1, 0), 'distance': (0, 1, 0, 0),
    'speed': (0, 1, -1, 0), 'acceleration': (0, 1, -2, 0),
    'force': (1, 1, -2, 0), 'work': (1, 2, -2, 0),
    'voltage': (1, 2, -3, -1), 'potential difference': (1, 2, -3, -1),
    'resistance': (1, 2, -3, -2),
}


def check_formula_dimensions(expression, bindings):
    """Check explicit scalar algebra under supplied symbol -> quantity assumptions.

    No eval, inferred symbols, implicit multiplication, functions, or unit conversion.
    A consistent result cannot detect a wrong sign, coefficient, or physical law.
    """
    result = dict(status='NOT_ASSESSED', policy='bounded_si_dimensions_v1',
                  binding_assumptions=dict(bindings), dimension_basis=['mass','length','time','current'],
                  formula_verified=False, domain_checked=False)
    class Mismatch(ValueError):
        pass
    def dimension(node):
        if isinstance(node, ast.Name) and node.id in bindings:
            label = bindings[node.id]
            if label in DIMENSIONS:
                return DIMENSIONS[label]
        elif isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return (0, 0, 0, 0)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return dimension(node.operand)
        elif isinstance(node, ast.BinOp):
            left = dimension(node.left)
            if isinstance(node.op, ast.Pow):
                exponent = node.right
                sign = 1
                if isinstance(exponent, ast.UnaryOp) and isinstance(exponent.op, (ast.USub, ast.UAdd)):
                    sign = -1 if isinstance(exponent.op, ast.USub) else 1
                    exponent = exponent.operand
                if not (isinstance(exponent, ast.Constant) and type(exponent.value) is int
                        and abs(exponent.value) <= 12):
                    raise ValueError('Only bounded integer exponents are supported')
                return tuple(v * sign * exponent.value for v in left)
            right = dimension(node.right)
            if isinstance(node.op, (ast.Add, ast.Sub)):
                if left != right:
                    raise Mismatch('Addition or subtraction combines different dimensions')
                return left
            if isinstance(node.op, (ast.Mult, ast.Div)):
                sign = -1 if isinstance(node.op, ast.Div) else 1
                return tuple(a + sign*b for a,b in zip(left,right))
        raise ValueError('Unsupported expression or unbound quantity symbol')
    try:
        if (not isinstance(expression, str) or len(expression) > 256
                or expression.count('=') != 1
                or not re.fullmatch(r'[A-Za-z0-9\s=+*/().^\-]+', expression)):
            raise ValueError('Requires one bounded explicit algebraic equality')
        sides = [ast.parse(s.strip().replace('^','**'), mode='eval') for s in expression.split('=')]
        if sum(len(list(ast.walk(s))) for s in sides) > 100:
            raise ValueError('Expression exceeds supported complexity')
        # Reject unknown symbols before comparing any subexpression dimensions.
        names = {n.id for s in sides for n in ast.walk(s) if isinstance(n, ast.Name)}
        if any(name not in bindings or bindings[name] not in DIMENSIONS for name in names):
            raise ValueError('Every symbol requires a recognized quantity binding')
        left, right = [dimension(s.body) for s in sides]
        result.update(left_dimension=left, right_dimension=right,
                      status='CONSISTENT_UNDER_BINDINGS' if left == right else 'DIMENSION_MISMATCH')
    except Mismatch as exc:
        result.update(status='DIMENSION_MISMATCH', reason=str(exc))
    except (ValueError, SyntaxError, RecursionError) as exc:
        result['reason'] = str(exc)
    return result


def check_region_dimensions(packet):
    """Use literal nearby mentions only as provisional binding assumptions."""
    blocked = dict(status='NOT_ASSESSED', policy='bounded_si_dimensions_v1',
                   formula_verified=False, symbol_bindings_verified=False)
    if packet.get('clipped_span_count', 1) or packet.get('source_role') != 'unclassified_source':
        return {**blocked, 'reason': 'Clipped, example, or unclassified role metadata unavailable'}
    bindings = {}
    context = packet.get('preceding_layout_text', '')
    if re.search(r'\b(?:not|never|incorrect|wrong)\b', context, re.I):
        return {**blocked, 'reason': 'Nearby negation requires semantic review'}
    literal = quantity_symbol_mentions([dict(content=context, evidence_id=0,
        start_offset=0, end_offset=len(context))])
    supported = {(m['symbol'], m['name'], m['source_phrase']) for m in literal}
    for mention in packet.get('symbol_mentions', []):
        symbol, label = mention['symbol'], mention['label'].lower()
        phrase = mention.get('source_phrase', '')
        if (symbol, label, phrase) not in supported:
            return {**blocked, 'reason': 'Binding does not match a recognized nearby source phrase'}
        if symbol in bindings and bindings[symbol] != label:
            return {**blocked, 'reason': 'Conflicting nearby symbol labels'}
        bindings[symbol] = label
    return {**check_formula_dimensions(packet['layout_text'], bindings),
            'symbol_bindings_verified': False,
            'binding_source': 'nearby literal mentions; provisional associations',
            'dimension_source': 'built-in SI quantity registry; not extracted source evidence'}
