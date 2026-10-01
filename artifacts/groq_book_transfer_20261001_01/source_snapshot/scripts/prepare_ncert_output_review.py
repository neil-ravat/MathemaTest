"""Hide arm labels and retrieval metadata after predictions and AI references lock."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.prepare_ncert_review_packet import write_frozen


def blind_rows(results, cases):
    mapping = {c['original_case_id']: c for c in cases}
    expected = {(k, arm) for k in mapping for arm in ('direct', 'vector', 'graph')}
    pairs = [(r['case_id'], r['mode']) for r in results]
    if len(pairs) != len(set(pairs)) or set(pairs) != expected:
        raise ValueError('All scheduled case/arm records must be retained exactly once')
    shuffled = list(results)
    random.Random(7319).shuffle(shuffled)
    packet, key = [], []
    for i, row in enumerate(shuffled, 1):
        output_id = f'OUTPUT-{i:02d}'
        case = mapping[row['case_id']]
        aliases = {p['id']: f'P{j}' for j, p in enumerate(row.get('context', []), 1)}
        judgment = deepcopy(row.get('judgment'))
        if judgment:
            judgment['cited_passage_ids'] = [aliases.get(p, 'INVALID_CITATION') for p in judgment['cited_passage_ids']]
            # Free text can mention original IDs; remove their machine-specific form.
            for field in ('answer', 'reason'):
                if isinstance(judgment.get(field), str):
                    for old, new in sorted(aliases.items(), key=lambda item: -len(item[0])):
                        judgment[field] = judgment[field].replace(old, new)
        packet.append(dict(output_id=output_id, case_id=case['case_id'],
            operational_status=row['status'], judgment=judgment,
            evidence_policy='SOURCE_UNAVAILABLE' if row['mode'] == 'direct' else 'SOURCE_REQUIRED',
            context=[dict(id=aliases[p['id']], text=p['content'],
                start_offset=p['metadata']['start_offset'], end_offset=p['metadata']['end_offset'])
                for p in row.get('context', [])]))
        key.append(dict(output_id=output_id, case_id=row['case_id'], mode=row['mode']))
    return packet, key


def build(run, references, output):
    lock_path = run / 'prediction_lock.json'
    lock = json.loads(lock_path.read_text())
    if lock.get('predictions_frozen') is not True or not lock.get('hashes'):
        raise ValueError('Completed prediction hash lock required')
    for relative, expected in lock['hashes'].items():
        path = (run / relative).resolve()
        if not path.is_relative_to(run.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f'Prediction lock mismatch: {relative}')
    required = ('reviewer_A_ai.json', 'reviewer_B_ai.json', 'adjudicated_ai_reference.json', 'cases.json')
    reference_hashes = {name: hashlib.sha256((references / name).read_bytes()).hexdigest() for name in required}
    packet, key = blind_rows(json.loads((run / 'results.json').read_text()),
                            json.loads((references / 'cases.json').read_text()))
    def save(name, data):
        write_frozen(output / name, json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    save('scoring_packet.json', dict(reference_directory=str(references), outputs=packet,
        blinding_limit='Arm names and retrieval provenance hidden; direct policy, empty context and failures can reveal arm class. Shared AI family; not expert gold.'))
    save('unblinding_key_DO_NOT_OPEN_DURING_REVIEW.json', key)
    save('manifest.json', dict(prediction_lock_sha256=hashlib.sha256(lock_path.read_bytes()).hexdigest(),
        reference_hashes=reference_hashes, count=len(packet), shuffle_seed=7319, expert_gold=False))
    print(f'Prepared {len(packet)} shuffled output records; arm key kept separate.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--references', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.run.resolve(), args.references.resolve(), args.output.resolve())
