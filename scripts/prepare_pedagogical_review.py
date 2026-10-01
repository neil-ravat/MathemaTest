"""Prepare assisted, unlabeled development review; never fresh or expert gold."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.prepare_ncert_review_packet import write_frozen

CHECKLISTS={
 '11.1': [('Relating charge to current and time','Does the earlier material explain how these three quantities are related?'),
          ('Changing minutes to seconds','Is this stated earlier, or would you explicitly assume the learner already knows it?'),
          ('Rearranging and multiplying','Would the learner already know the arithmetic/algebra needed to use the relationship?')],
 '11.2': [('Relating work, charge and potential difference','Does the earlier material explain the relationship between these quantities?'),
          ('Rearranging and multiplying','Would the learner already know how to use that relationship to find work?')],
 '11.4': [('Relating voltage, current and resistance','Is the relationship taught before this question?'),
          ('When resistance stays constant','Is the condition for using the same resistance at both voltages adequately explained? Mark unsure if this needs physics expertise.'),
          ('Using the relationship for the new voltage','Would the learner already know the arithmetic/algebra needed?')],
}


def build(output,source=ROOT/'data/ncert10_pilot_v1'):
    cases=json.loads((source/'live_development_cases_v1.json').read_text())
    rows=[];index=['# Pedagogical review — start here','','These three cases are exposed development material. This is assisted review: proposed knowledge checklists are supplied by AI. No model answers or gap predictions are included. Your reviews are not automatically expert gold.','','For each item choose **EARLIER** (quote earlier teaching), **BACKGROUND** (explicitly assumed learner knowledge), **NOT_FOUND** (you did not find it), or **UNSURE**. NOT_FOUND is not proof of a teaching gap.','','Decisions: **SUPPORTED** under your stated background, **GAP** only after a complete curriculum review, otherwise **UNCERTAIN**. The current packet does not contain a complete earlier-grade curriculum, so an attempted GAP decision is retained as a suggestion but cannot become a validated gap label.','']
    for c in cases:
        raw=(source/'raw'/f"{c['source_id']}.txt").read_text()
        pdf=source/'raw'/f"{c['source_id']}.pdf"
        if hashlib.sha256(raw.encode()).hexdigest()!=c['source_text_sha256'] or hashlib.sha256(pdf.read_bytes()).hexdigest()!=c['source_pdf_sha256']:
            raise ValueError('Source hash mismatch')
        if raw[c['target_start_offset']:c['target_end_offset']]!=c['target_raw']:
            raise ValueError('Target slice mismatch')
        name='example-'+c['example'].replace('.','-')
        prefix=raw[:c['target_start_offset']]
        write_frozen(output/f'{name}-earlier.txt',prefix)
        row={k:c[k] for k in ['id','source_id','pdf_page','printed_page','source_pdf_sha256','source_text_sha256','target_start_offset','target_end_offset','target_raw']}
        row.update(earlier_context_file=f'{name}-earlier.txt',prefix_sha256=hashlib.sha256(prefix.encode()).hexdigest(),
                   context_complete_for_curriculum=False,review_type='ASSISTED_DEVELOPMENT',expert_gold=False)
        rows.append(row)
        checklist=CHECKLISTS[c['example']]
        form=dict(case_id=c['id'],reviewer='',learner_background='',input_readable=None,prerequisites_complete=None,
            judgment=None,rationale='',requirements=[dict(name=n,status=None,quote='',background_reason='') for n,_ in checklist])
        write_frozen(output/f'{name}-blank.json',json.dumps(form,indent=2)+'\n')
        text=[f"# Example {c['example']} — printed page {c['printed_page']}",'',
              '## Question as extracted','', '```text',c['target_raw'].strip(),'```','',
              f'[Full earlier chapter text]({name}-earlier.txt)', '',
              f'[Original PDF, page {c["pdf_page"]}]({pdf.resolve()})', '',
              'Check the PDF if text or equations look damaged. The original PDF includes later solutions: never cite those as earlier teaching. This excerpt includes no target answer.', '',
              '## Your checks','',
              '1. Is the question and its notation readable? Yes / No / Unsure.',
              '2. State what this learner is already expected to know. If you cannot judge, say unsure.',
              '3. Review each suggested knowledge item below. Add anything missing; the AI list may be incomplete.','']
        for n,q in checklist:text += [f'- **{n}:** {q} Choose EARLIER / BACKGROUND / NOT_FOUND / UNSURE. Quote support, or explain the background assumption.']
        text += ['', '4. Is this knowledge list complete? Yes / No / Unsure.',
                 '5. Your overall decision: SUPPORTED / GAP / UNCERTAIN, with a reason.', '',
                 'You may reply in chat using these headings. Leave scientific judgments unsure when necessary. A symbol-label approval does not answer these questions.', '',
                 f'Optional structured form: [{name}-blank.json]({name}-blank.json).']
        write_frozen(output/f'{name}.md','\n'.join(text)+'\n')
        index += [f"- [Example {c['example']}]({name}.md)"]
    write_frozen(output/'cases.json',json.dumps(rows,indent=2)+'\n')
    write_frozen(output/'START_HERE.md','\n'.join(index)+'\n')
    files=[p for p in output.iterdir() if p.is_file() and p.name!='manifest.json']
    write_frozen(output/'manifest.json',json.dumps(dict(case_count=len(rows),heldout=False,expert_gold=False,
        completed_reviews=0,builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}),indent=2)+'\n')
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Use a new output directory')
    build(args.output)
    print(args.output/'START_HERE.md')
