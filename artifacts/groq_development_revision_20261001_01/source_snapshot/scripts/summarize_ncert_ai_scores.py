"""Summarize frozen AI labels with all-case denominators and chapter bootstrap."""
import argparse
from collections import Counter
import json
from pathlib import Path
import random
import statistics


def summarize(scores, key, cases, results):
    labels = {r['output_id']: r for r in scores}
    if len(labels) != len(scores) or set(labels) != {r['output_id'] for r in key}:
        raise ValueError('Every shuffled output requires one adjudicated label')
    sources = {c['id']: c['source_id'] for c in cases}
    operational = {(r['case_id'], r['mode']): r for r in results}
    expected = {(c, m) for c in sources for m in ('direct', 'vector', 'graph')}
    if set(operational) != expected or len(results) != len(expected):
        raise ValueError('Incomplete scheduled-arm denominator')
    rows = []
    categories = {'COMPLETE', 'PARTIAL', 'INCORRECT', 'ABSTAIN', 'ERROR', None}
    for identity in key:
        r = {**identity, **labels[identity['output_id']]}
        if r['answer_category'] not in categories:
            raise ValueError('Unknown answer category')
        if r['answer_category'] is None and r.get('reference_resolvable', True):
            raise ValueError('Null answer category requires unresolved reference')
        op = operational[(identity['case_id'], identity['mode'])]
        if op['status'] in ('ERROR', 'REJECTED_CALCULATION') and r['answer_category'] != 'ERROR':
            raise ValueError('Runner failure cannot be rescued as an accepted answer')
        r.update(case_id=identity['case_id'], mode=identity['mode'], source_id=sources[identity['case_id']])
        r['full_correct'] = r['answer_category'] == 'COMPLETE'
        r['grounded_correct'] = r['full_correct'] and r['evidence_support'] == 'ADEQUATE' and r['mode'] != 'direct'
        rows.append(r)
    summary = {}
    for mode in ('direct', 'vector', 'graph'):
        arm = [r for r in rows if r['mode'] == mode]
        n = len(arm)
        correct = sum(r['full_correct'] for r in arm)
        unresolved = sum(r['answer_category'] is None for r in arm)
        elapsed = [operational[(r['case_id'], mode)]['latency_including_shared_vector_search_seconds'] for r in arm]
        summary[mode] = dict(scheduled=n, categories=dict(Counter(r['answer_category'] or 'UNCERTAIN_REFERENCE' for r in arm)),
            complete=correct, full_correct_proportion=correct/n,
            unresolved=unresolved, full_correct_bounds=[correct/n, (correct+unresolved)/n],
            grounded_correct=sum(r['grounded_correct'] for r in arm) if mode != 'direct' else None,
            evidence_categories=dict(Counter(r['evidence_support'] for r in arm)),
            median_solve_seconds=statistics.median(elapsed), total_solve_seconds=sum(elapsed))
    by_pair = {(r['case_id'], r['mode']): r for r in rows}
    paired = []
    for c, source in sources.items():
        vector, graph = by_pair[c, 'vector'], by_pair[c, 'graph']
        paired.append(dict(case_id=c, source_id=source,
            answer_difference=int(graph['full_correct'])-int(vector['full_correct']),
            grounded_difference=int(graph['grounded_correct'])-int(vector['grounded_correct'])))
    chapters = sorted(set(sources.values()))
    rng = random.Random(42)
    bootstrap = []
    for _ in range(10000):
        sampled = rng.choices(chapters, k=len(chapters))
        values = [r['grounded_difference'] for s in sampled for r in paired if r['source_id'] == s]
        bootstrap.append(sum(values)/len(values))
    bootstrap.sort()
    def percentile(p):
        at = (len(bootstrap)-1)*p
        lo = int(at)
        return bootstrap[lo]+(bootstrap[min(lo+1,len(bootstrap)-1)]-bootstrap[lo])*(at-lo)
    summary['paired'] = dict(cases=paired,
        grounded_wins=sum(r['grounded_difference'] == 1 for r in paired),
        grounded_losses=sum(r['grounded_difference'] == -1 for r in paired),
        grounded_ties=sum(r['grounded_difference'] == 0 for r in paired),
        grounded_mean_difference=sum(r['grounded_difference'] for r in paired)/len(paired),
        chapter_bootstrap95=[percentile(.025),percentile(.975)],
        per_chapter={s:dict(families=sum(r['source_id']==s for r in paired),
            grounded_mean_difference=statistics.mean(r['grounded_difference'] for r in paired if r['source_id']==s)) for s in chapters},
        bootstrap_seed=42, bootstrap_resamples=10000,
        interpretation='Descriptive convenience-sample interval with few chapters, not confirmatory inference; structural graph future exposure and AI-label limits apply')
    summary['reference_type'] = 'AI_REFERENCE_NOT_EXPERT_GOLD'
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('scores','key','cases','results','output'):
        parser.add_argument('--'+name, type=Path, required=True)
    a = parser.parse_args()
    read = lambda p: json.loads(p.read_text())
    value = summarize(read(a.scores)['labels'], read(a.key), read(a.cases), read(a.results))
    encoded = json.dumps(value, indent=2)+'\n'
    if a.output.exists() and a.output.read_text() != encoded:
        raise ValueError('Refusing to overwrite different summary')
    a.output.write_text(encoded)
