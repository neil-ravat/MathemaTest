"""Narrow public-text integer source analysis and filtering of saved LLM evidence.

This is a grammar-limited source solver, not general mathematical verification.
No case labels, oracle structures, or benchmark-specific identifiers are consumed.
"""
import ast
import re

from scripts.run_decomposed_study import Evidence, calculate, decide

NAME = r'[A-Za-z_][A-Za-z_0-9]*'
DEFINITION = re.compile(rf'^(?:Define\s+|For integer x, the rule is\s+)?({NAME})\(x\)\s*=\s*(.+?)\.?$')
EQUALITY = re.compile(r'^(?:Check the equality\s+|The proposed result is\s+)?(.+?)\s*=\s*([+-]?\d+)\s*\.?$')
BACKGROUND = re.compile(
    rf'Integer (?:arithmetic|addition) and equality(?:\.|'
    rf'; (?:{NAME}(?:, | and |, and ))*{NAME} are unfamiliar textbook-specific function names\.)?'
    r'(?: Function names are local to this curriculum\.)?')
PREVIEW = re.compile(
    rf'Preview: {NAME} will be (?:used|defined) later\. No calculation or proof is (?:asserted|required) here\.|'
    rf'Preview only: a function called {NAME} will be defined later; no calculation or proof is required here\.', re.I)
MAX_NODES = 256
MAX_DEPTH = 48


class Unsupported(ValueError):
    pass


def parse_expression(text, *, variables=True, calls=True):
    if len(text) > 2000:
        raise Unsupported('expression_length_bound')
    tree = ast.parse(text.strip(), mode='eval').body
    if any(i >= MAX_NODES for i, _ in enumerate(ast.walk(tree))):
        raise Unsupported('expression_node_bound')

    def check(node, depth=0):
        if depth > MAX_DEPTH:
            raise Unsupported('expression_depth_bound')
        if isinstance(node, ast.Constant) and type(node.value) is int:
            if abs(node.value) > 10**12:
                raise Unsupported('integer_bound')
        elif variables and isinstance(node, ast.Name) and node.id == 'x':
            pass
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            check(node.operand, depth+1)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult)):
            check(node.left, depth+1); check(node.right, depth+1)
        elif (calls and isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
              and re.fullmatch(NAME, node.func.id) and len(node.args) == 1 and not node.keywords):
            check(node.args[0], depth+1)
        else:
            raise Unsupported('unsupported_expression_syntax')
    check(tree)
    return tree


def structure(node):
    """Normalize association only for +/*, preserving order and every literal."""
    if isinstance(node, ast.Constant):
        return ['integer', node.value]
    if isinstance(node, ast.UnaryOp):
        return ['positive' if isinstance(node.op, ast.UAdd) else 'negative', structure(node.operand)]
    operation = 'add' if isinstance(node.op, ast.Add) else 'multiply' if isinstance(node.op, ast.Mult) else 'subtract'
    a, b = structure(node.left), structure(node.right)
    if operation == 'subtract':
        return [operation, a, b]
    return [operation, *(a[1:] if a[0] == operation else [a]), *(b[1:] if b[0] == operation else [b])]


def source_analysis(payload):
    """Return serializable source-only analysis; unsupported/ambiguous inputs abstain."""
    result = dict(supported=False, target_kind='other', source_status='ABSTAIN',
                  required_passage_ids=[], missing_functions=[], expanded_expression=None,
                  arithmetic_structure=None, computed_value=None, claimed_value=None, reason=None)
    try:
        target = payload['target'].strip()
        if not BACKGROUND.fullmatch(payload['background_knowledge'].strip()):
            raise Unsupported('unsupported_background')
        # Require a complete preview sentence without an embedded equality assertion.
        if PREVIEW.fullmatch(target):
            result.update(supported=True, target_kind='preview', source_status='PASS')
            return result
        match = EQUALITY.fullmatch(target)
        if not match:
            raise Unsupported('unsupported_target')
        claimed = int(match.group(2))
        if abs(claimed) > 10**12:
            raise Unsupported('integer_bound')
        result.update(target_kind='equality', claimed_value=claimed)
        target_tree = parse_expression(match.group(1), variables=False)
        def check_background(tree):
            if payload['background_knowledge'].startswith('Integer addition') and any(
                isinstance(n, (ast.Sub, ast.Mult)) or
                (isinstance(n, ast.UnaryOp) and not isinstance(n.operand, ast.Constant))
                for n in ast.walk(tree)
            ):
                raise Unsupported('unsupported_background_operation')
        check_background(target_tree)
        all_passages = [*payload['context'], *payload['background_passages']]
        ids = [d['id'] for d in all_passages]
        if len(set(ids)) != len(ids):
            raise Unsupported('ambiguous_passage_id')
        passages = [d for d in payload['context'] if d['position'] < payload['target_position']]
        passages += payload['background_passages']
        if len(passages) > 256:
            raise Unsupported('passage_count_bound')
        definitions = {}
        for passage in passages:
            definition = DEFINITION.fullmatch(passage['content'].strip())
            if not definition:
                raise Unsupported('unsupported_source_passage')
            name, expression = definition.groups()
            if name in definitions:
                raise Unsupported('ambiguous_definition')
            body = parse_expression(expression)
            check_background(body)
            definitions[name] = (passage['id'], body)
        required, missing = set(), set()
        visited = 0

        def expand(node, argument=None, stack=(), depth=0):
            nonlocal visited
            visited += 1
            if visited > 1024 or depth > MAX_DEPTH:
                raise Unsupported('expansion_resource_bound')
            if isinstance(node, ast.Constant):
                return node
            if isinstance(node, ast.Name):
                if argument is None:
                    raise Unsupported('unbound_variable')
                return argument
            if isinstance(node, ast.UnaryOp):
                value = expand(node.operand, argument, stack, depth+1)
                return ast.UnaryOp(op=node.op, operand=value) if value is not None else None
            if isinstance(node, ast.BinOp):
                a = expand(node.left, argument, stack, depth+1)
                b = expand(node.right, argument, stack, depth+1)
                return ast.BinOp(left=a, op=node.op, right=b) if a is not None and b is not None else None
            name = node.func.id
            value = expand(node.args[0], argument, stack, depth+1)
            if name in stack:
                raise Unsupported('cyclic_definition')
            if name not in definitions:
                missing.add(name)
                return None
            passage_id, body = definitions[name]
            required.add(passage_id)
            # Continue traversing definitions even after a missing argument, to detect
            # independent missing dependencies and cycles before claiming a gap.
            expanded = expand(body, value if value is not None else ast.Constant(value=0), stack+(name,), depth+1)
            return expanded if value is not None else None

        expanded = expand(target_tree)
        result.update(required_passage_ids=sorted(required), missing_functions=sorted(missing))
        if missing:
            result.update(supported=True, source_status='FAIL_GAP' if payload['context_complete'] else 'ABSTAIN')
        else:
            if any(i >= MAX_NODES for i, _ in enumerate(ast.walk(expanded))):
                raise Unsupported('expanded_expression_node_bound')
            expression = ast.unparse(ast.fix_missing_locations(expanded))
            value = calculate(expression)
            result.update(supported=True, expanded_expression=expression,
                          arithmetic_structure=structure(expanded), computed_value=value,
                          source_status='PASS' if value == claimed else 'FAIL_LOGIC')
    except (Unsupported, SyntaxError, ValueError, KeyError, TypeError, AttributeError, RecursionError, OverflowError) as exc:
        result.update(supported=False, source_status='ABSTAIN', reason=str(exc))
    return result


def guard_evidence(evidence, payload):
    """Accept only source-matching old valid evidence; prior decoder errors propagate.

Rejected evidence becomes ABSTAIN, never the solver's alternative answer.
All used definitions must be cited and missing-name sets must match; values alone
are insufficient. Associative regrouping of +/* is allowed, reordering is not.
"""
    original, _ = decide(evidence, payload)
    e = Evidence.model_validate(evidence)
    source = source_analysis(payload)
    reason = None
    if not source['supported']:
        reason = 'unsupported_source'
    elif e.target_kind != source['target_kind'] or e.claimed_value != source['claimed_value']:
        reason = 'target_mismatch'
    elif (len(e.missing_prerequisites) != len(set(e.missing_prerequisites)) or
          set(e.missing_prerequisites) != set(source['missing_functions'])):
        reason = 'missing_prerequisites_mismatch'
    elif (len(e.cited_passage_ids) != len(set(e.cited_passage_ids)) or
          not set(source['required_passage_ids']) <= set(e.cited_passage_ids)):
        reason = 'citations_mismatch'
    elif source['expanded_expression'] is not None:
        if e.calculation is None:
            reason = 'calculation_missing'
        else:
            try:
                if structure(parse_expression(e.calculation, variables=False, calls=False)) != source['arithmetic_structure']:
                    reason = 'calculation_structure_mismatch'
            except (Unsupported, SyntaxError, RecursionError):
                reason = 'calculation_unsupported'
    elif e.calculation is not None:
        reason = 'unexpected_calculation'
    if reason is None and original['status'] != source['source_status']:
        reason = 'verdict_mismatch'
    verdict = original if reason is None else {
        'status': 'ABSTAIN', 'reason': 'Source guard rejected evidence: '+reason,
        'missing_prerequisites': [], 'cited_passage_ids': [],
    }
    return {'verdict': verdict, 'accepted': reason is None, 'rejection_reason': reason, 'source': source}
