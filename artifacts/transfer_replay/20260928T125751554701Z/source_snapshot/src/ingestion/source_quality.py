"""Conservative source cues; neither semantic validation nor equation recognition."""
import re


def is_worked_example(text):
    # ponytail: explicit headings only; unmarked continuations need layout metadata.
    return bool(re.search(r'^\s*(?:Example\s+\d+(?:\.\d+)*\b|Solution\b)', text, re.I | re.M))


def formula_candidates(units):
    """Keep original equation-containing excerpts and offsets, without guessing math.

    This includes stacked/ambiguous equations so missing formula coverage is visible.
    A candidate must never be promoted to a verified formula merely for containing '='.
    """
    return [{**u, 'status': 'FORMULA_REVIEW_REQUIRED', 'formula_layout_verified': False}
            for u in units if '=' in u['content'] and not is_worked_example(u['content'])
            and not u['content'].rstrip().endswith('?')]


def quantity_symbol_mentions(units):
    """Read explicit scalar-quantity/symbol phrases; no inferred formula or unit edge.

    Bounded vocabulary prevents arbitrary words beside letters becoming quantities.
    Only the printed phrase is asserted, not a symbol assignment or definition.
    Negated or conditional occurrences retain that same literal-only status.
    """
    labels = r'electric charge|electric current|potential difference|charge|current|time|resistance|voltage|work done|work|force|distance|speed|acceleration'
    pattern = re.compile(rf'\b(?P<label>(?i:{labels}))\s+(?:\((?P<parenthesized>[A-Za-z])\)|(?P<bare>[A-Zb-z])(?=\s*[,;.]|\s+and\b|$))')
    inverse = re.compile(rf'\b(?P<symbol>[A-Zb-z]),?\s+for\s+(?:the\s+)?(?P<label>(?i:{labels}))(?!\w)')
    found = []
    for unit in units:
        if is_worked_example(unit['content']) or unit['content'].rstrip().endswith('?'):
            continue
        for match in sorted([*pattern.finditer(unit['content']), *inverse.finditer(unit['content'])], key=lambda m:m.start()):
            label = match['label'].lower()
            found.append(dict(name='work' if label == 'work done' else label,
                symbol=(match.groupdict().get('symbol') or match.groupdict().get('parenthesized') or match.groupdict().get('bare')), evidence_id=unit['evidence_id'],
                source_phrase=match.group(), start_offset=unit['start_offset']+match.start(),
                end_offset=unit['start_offset']+match.end()))
    return found
