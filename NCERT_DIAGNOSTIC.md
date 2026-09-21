# NCERT selected-context diagnostic

## Completed pilot

All 24 local calls completed, with no retries or truncated responses. Five focused preparation/validation tests passed. All fifteen original source-package files and all five frozen diagnostic files remained unchanged. The final input-token maximum was 3,073, below the 8,192-token context budget; maximum output was 852 tokens, below the 1,600-token limit.

| Model | Fully correct answers | Maths | Electricity | Schema-valid responses |
|---|---:|---:|---:|---:|
| Qwen2.5-Coder 7B | 5/12 | 2/6 | 3/6 | 12/12 |
| Mistral (installed `latest` digest recorded) | 3/12 | 1/6 | 2/6 | 11/12 |

These are AI-audited answer counts for twelve curated development cases, independently crosschecked by another AI reviewer. They are not prerequisite-detection accuracy or teacher-validated educational results. Answers stated in reasoning were credited even when the structured answer field was null; contradictory answers were not counted fully correct. This coding detail was clarified during review. Correct final answers and sound reasoning were assessed separately.

Both configurations are unreliable under this combined prompt. Qwen sometimes gives a correct answer through a false derivation. Mistral mistakes supplied quantities and, in one case, falsely demands a numerical resistivity even though it cancels. Citation IDs exist, but that does not establish that the cited passage supports the claim. These are failures of the model responses, not demonstrated textbook defects.

The next useful experiment is to separate prerequisite evidence mapping from solving and independently check the resulting algebra and units. It should be a new, versioned development run; this baseline remains preserved. This pilot alone cannot establish whether the failure originates in model capability, prompt design or their interaction.

- [Detailed case-level review](artifacts/ncert10_diagnostic/20260919T235017330481Z/AI_REVIEW.md)
- [Machine-readable review summary](artifacts/ncert10_diagnostic/20260919T235017330481Z/review_summary.json)
- [Raw requests and responses](artifacts/ncert10_diagnostic/20260919T235017330481Z/predictions.jsonl)
- [Frozen clean inputs](data/ncert10_diagnostic_v1/payloads.json)
- [Final integrity checks](artifacts/ncert10_diagnostic/20260919T235017330481Z/FINAL_QA.json)

## Frozen design

Twelve worked-example questions: six from Quadratic Equations and six from Electricity, in the official pinned NCERT Reprint 2026-27 chapters. Each of two local models receives the same twelve inputs once: `qwen2.5-coder:7b` and `mistral:latest`. This is a convenience development sample with no human educational labels.

The task is to map prerequisite evidence and attempt the question. It is not an audit of complete curricular coverage, a retrieval benchmark, or a formal proof task. No synthetic held-out data is used.

The original sources and raw extraction remain unchanged. A separate diagnostic version contains fifteen AI-reviewed source summaries: nine Maths and six Science passages, with exact original-text anchors and offsets. Equations, fractions, radicals and the complete printed Table 11.2 have been visually checked. These are faithful normalized summaries, not verbatim transcriptions or full chapter prefixes. Full table values are retained as printed; they have not been certified against external physical measurements.

Within each subject, a case receives all selected passages that finish before its question begins. Earlier worked examples are legitimate prior instruction; the target's own solution and later passages are excluded. Excerpts were curated before predictions, informed by the inspection, so the study measures performance with curated evidence and cannot estimate automatic retrieval quality. Same-page source images containing answers are never supplied to the models.

All Maths cases share declared algebra, real-number/square-root and geometry background. All Science cases share declared arithmetic, SI conversion, circular-area and table-reading background. These are experimental learner assumptions, not claims about what a particular pupil has learned. Physical conditions remain in the original source-derived passages, including the constant-temperature qualification for Ohm's law.

## Execution and review

Local Ollama native chat API; JSON output mode; temperature 0; seed 42; context budget 8192 tokens; maximum generated tokens 1600. One call per case/model, no retries or prompt tuning after seeing outputs. Models run in batches to avoid repeatedly swapping weights. Actual installed model digests, requests, raw responses, finish reasons, timing and hashes are retained. A temperature of zero and seed do not guarantee cross-platform bitwise reproducibility.

The strict output schema requests prerequisites with support type and evidence IDs, assumptions, attempted answer or abstention, calculation reasoning and unresolved requirements. Mechanical checks distinguish schema validity from citation-ID validity and support-kind consistency. A valid citation ID does not establish that the passage supports its associated claim.

Before predictions, James authored a separate review reference for all twelve answers, important reasoning checks, physical assumptions and scope limitations. It is never included in the model payloads. Subsequent answer/reasoning review is AI-assisted, not teacher-validated gold. Correct final answers can coexist with faulty reasoning or unsupported citations. Report those dimensions separately.

No prerequisite-detection accuracy, textbook-defect prevalence, educational effectiveness, or formal verification claim follows from this diagnostic. Model familiarity with public NCERT material cannot be excluded by withholding the solution. The study has no no-context baseline or deliberately missing-evidence arm and therefore cannot establish causal benefit from supplying these passages.

## Reproduce

Preparation refuses changed frozen files. The native local server must have both named models available.

```sh
.venv/bin/python scripts/run_ncert_diagnostic.py prepare
.venv/bin/python -m pytest -q tests/test_ncert_diagnostic.py tests/test_ncert_pilot.py
.venv/bin/python scripts/run_ncert_diagnostic.py run
```

Inputs: `data/ncert10_diagnostic_v1/`. Execution artifacts: timestamped directories under `artifacts/ncert10_diagnostic/`. Source curation and pre-inference review: `artifacts/ncert10_pilot_v1/curation/`.
