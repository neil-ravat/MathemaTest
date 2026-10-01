"""Create exploratory corruption controls and a separately blinded review packet."""
import argparse
import hashlib
import json
from pathlib import Path
import random

ROOT=Path(__file__).resolve().parents[1]


def cases():
    work='Find the work done moving a charge of 3 C across a potential difference of 9 V.'
    lens='A thin converging lens has focal length +0.25 m. Find its power in dioptres.'
    rows=[]
    for family,question,source,value,units,missing,damaged,wrong in [
        ('work',work,'V = W/Q\nPotential difference V is work W in joules divided by charge Q in coulombs.','27',['j','joule','joules'],
         'Charge is measured in coulombs. Potential difference is measured in volts.',
         'V = W/[unreadable symbol].',work.replace('3 C','3 kg')),
        ('lens',lens,'P = 1/f\nLens power P is in dioptres when focal length f is in metres.','4',['d','dioptre','dioptres','diopter','diopters'],
         'A converging lens has positive focal length. Focal length is a distance.',
         'P = [unreadable symbol]/f. Power P is in dioptres; focal length f is in metres.',lens.replace('0.25 m','0.25 seconds'))]:
        for operator,q,s in [('clean',question,source),('missing_rule',question,missing),
                              ('damaged_symbol',question,damaged),('wrong_unit',wrong,source)]:
            row=dict(id=family+'_'+operator,family=family,operator=operator,question=q,source=s,
                     expected='answer' if operator=='clean' else 'withhold')
            if operator=='clean':row.update(value=value,units=units)
            rows.append(row)
    return rows


def blinded(rows):
    order=list(rows);random.Random(20260928).shuffle(order)
    return [dict(id=f'R{i:02}',question=c['question'],source=c['source'],
                 background='Rational arithmetic; 1 minute = 60 seconds; SI units multiply and divide with quantities.')
            for i,c in enumerate(order,1)], {f'R{i:02}':c['id'] for i,c in enumerate(order,1)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    rows=cases();packet,key=blinded(rows)
    private=args.output/'coordinator_only';private.mkdir()
    public=args.output/'reviewer_packet';public.mkdir()
    (private/'cases.json').write_text(json.dumps(rows,indent=2))
    (private/'blind_key.json').write_text(json.dumps(key,indent=2))
    (private/'protocol.md').write_text('''# Prespecified exploratory corruption study

Two exposed subject families (work and lens power), each with clean, missing-rule,
unreadable-symbol and incompatible-input-unit versions: eight scheduled attempts.
No retries or mid-run tuning. These are controlled text corruptions, not measured
PDF/OCR failures. Each control changes one supplied component relative to its base.
Use the production auditor and controlled passages; extraction/retrieval are not
evaluated. No curricular-gap inference is authorized. All cases remain development.
Source-only policy: a damaged/absent rule may not be filled from model memory;
incompatible input units require withholding. References are AI-authored, awaiting
independent review. Score all eight attempts, report each operator separately,
retain invalid-output abstentions as validation failures. Count accepted answers on
corrupted cases as false acceptances under this prespecified evidence policy.
The runner freezes full source snapshots, cases, model metadata and prompt before
calls. Reviewer packet omits operators, references, model outputs and original IDs.
Give reviewers only reviewer_packet/, never coordinator_only/ or study outputs.
Blinding from outputs does not establish reviewer expertise or unfamiliarity with
the case families. Labels must be collected before exposing reviewers to predictions.
''')
    (public/'cases.json').write_text(json.dumps(packet,indent=2))
    forms=[dict(id=c['id'],reviewer_id=None,qualifications=None,input_readable=None,
                evidence_sufficient=None,answer=None,unit=None,required_assumptions=[],
                decision=None,supporting_quotes=[],reason=None,reviewed_at=None) for c in packet]
    (public/'responses.json').write_text(json.dumps(forms,indent=2))
    lines=['# Blinded development review','',
        'Review only the supplied question, source and background. No model predictions or expected labels are included.',
        'These are synthetic development materials; blinding does not make them an independent benchmark.',
        'For each case: is the input readable, is the evidence sufficient, what answer follows (if any), and what assumptions are required?',
        'Choose ANSWER_SUPPORTED, WITHHOLD or UNSURE. Quote the supplied evidence. Missing evidence does not prove a textbook defect.',
        'Record your qualifications and decision in responses.json. Leave scientific judgments UNSURE when outside your expertise.','']
    for c in packet:
        lines += ['## '+c['id'],'',c['question'],'','Supplied source:','',c['source'],'','Background: '+c['background'],'']
    (public/'START_HERE.md').write_text('\n'.join(lines))
    (private/'reviewer_packet_hashes.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in public.iterdir()},indent=2))
    print(private/'cases.json');print(public/'START_HERE.md')


if __name__=='__main__':main()
