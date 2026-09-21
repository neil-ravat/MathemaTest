# NCERT Class 10 pilot: sources prepared

NCERT is a useful next development setting because it supplies ordered lessons, worked examples, explicit references to previous grades, and mathematics involving units, tables, and diagrams. It is a substantial domain change from the synthetic integer-function experiments. The current source guard cannot interpret these textbooks as-is.

## Source scope

English-language official PDFs downloaded on 20 September 2026 (local date). All four files inspected through their extracted reprint markers say **Reprint 2026-27**; the selected chapter page images confirm that marking. This pins the downloaded versions, not a promise that the URLs will always serve identical files.

| Source | Scope | PDF pages | Printed pages |
|---|---|---:|---|
| [Class 10 Mathematics, Chapter 4](https://www.ncert.nic.in/textbook/pdf/jemh104.pdf) | Quadratic Equations | 11 | 38-48 |
| [Class 10 Science, Chapter 11](https://www.ncert.nic.in/textbook/pdf/jesc111.pdf) | Electricity | 24 | 171-194 |

The Class 10 Science book contains the physics material for this pilot. Mathematics and Science preliminaries were also downloaded to retain edition context. This is a two-chapter pilot, not an audit of both complete books. Sources remain local with their NCERT copyright; free access is not treated as an open redistribution license.

## Prepared locally

- Four original PDFs with official URLs, retrieval metadata and SHA-256 hashes.
- Page-ordered raw text for 35 chapter pages, with PDF and printed page locators. Text extraction is not mathematical transcription: all page-level formula QA flags remain incomplete.
- Twelve unlabeled candidate records, six per subject. Each stores the raw question, an AI visually reviewed question transcription, source hashes, reviewer notes, and exact character offsets for the earlier chapter prefix.
- Nine rendered pages inspected against all 12 selected questions. This review concerns the targets; it does not certify every earlier formula, table, or diagram.
- Question/solution boundary checks exclude the target's own worked solution and all later text from the proposed context. Earlier worked examples remain legitimate prior context. The prefix omits earlier chapters and grades, so full-curriculum context is explicitly marked incomplete.

| Candidate | PDF / printed page | Main review concern |
|---|---|---|
| Maths Example 2 | 3 / 40 | Algebraic identities and equation classification |
| Maths Example 3 | 5 / 42 | Explicit Class IX factorisation assumption |
| Maths Example 4 | 6 / 43 | Factorisation and fractional roots |
| Maths Example 5 | 6 / 43 | Radical notation lost by plain-text extraction |
| Maths Example 6 | 7 / 44 | Reference back to Section 4.1 and positive dimensions |
| Maths Example 7 | 8 / 45 | Discriminant and preceding quadratic formula |
| Electricity Example 11.1 | 2 / 172 | Current, charge, time, and unit conversion |
| Electricity Example 11.2 | 3 / 173 | Potential difference; solution continues on next page |
| Electricity Example 11.3 | 9 / 179 | Ohm law and a possible stale equation reference |
| Electricity Example 11.4 | 10 / 180 | Assumption of constant resistance |
| Electricity Example 11.5 | 10 / 180 | Resistivity, circular area, SI conversion, and table lookup |
| Electricity Example 11.6 | 10 / 180 | Resistance scaling with length and cross-section |

This is a convenience development sample selected before any NCERT model predictions. It is not representative of either book or suitable for estimating textbook defect prevalence. Questions are grouped by example, so examples with several subparts are not independent cases for each subpart.

## Initial source observations

1. The raw text for Maths Example 5 loses radical signs. The rendered page shows the square-root coefficient clearly. Feeding the uncorrected extraction to a model could manufacture a mathematical error. The reviewed target preserves it as `3*x^2-2*sqrt(6)*x+2=0`; the raw extraction is retained unchanged.
2. Maths Section 4.3 explicitly says factorisation by splitting the middle term was learnt in Class IX. Absence of a fresh derivation inside this chapter does not establish a prerequisite gap. Earlier Class IX sources and the specified learner background still need mapping before educational judgments.
3. Electricity Example 11.3(a) visibly cites Eq. (12.6), whereas part (b) cites Eq. (11.6). The chapter's Ohm-law relation is numbered (11.6). Record this as a candidate editorial cross-reference problem for review, not as a proven mathematical or prerequisite defect. Official errata and educational significance have not been checked.

## How the first diagnostic should work

First verify the earlier equations, tables, and required prior-chapter/grade material for these targets. Keep clean transcriptions traceable to the original page; never silently change a source formula. Record permitted background explicitly. A retrieved subset or this chapter-only prefix cannot support a full-curriculum absence claim.

Next use a consistent rubric separating adequate support, reasonable assumed knowledge, deliberate previews, missing prerequisites, mathematical errors, editorial cross-reference issues, and insufficient/extraction-damaged evidence. Two independent mathematics/science reviewers should supply rationales before adjudication. AI review can assist development but cannot substitute for independent teacher validation.

Only then freeze the diagnostic inputs and run the two models. Without educational labels, report output validity, evidence citation quality, extraction failures and abstentions, not prerequisite-detection accuracy. Numerical answer correctness and curricular adequacy are different outcomes. Keep target solutions and reviewer annotations out of model inputs. Public NCERT material may already be familiar to pretrained models; source order alone does not remove that knowledge.

Do not rewrite the checker into a collection of rules for these 12 questions merely to obtain a high score. Define any domain extension and its standalone symbolic baseline separately. If constructed omissions are added later, label them as interventions, keep them separate from natural textbook issues, and check that equivalent support is not still available elsewhere.

## Files and reproducibility

- [Dataset manifest](data/ncert10_pilot_v1/manifest.json)
- [Unlabeled candidates and visual review notes](data/ncert10_pilot_v1/candidates.json)
- [Builder](scripts/prepare_ncert_pilot.py)

```sh
.venv/bin/python scripts/prepare_ncert_pilot.py
.venv/bin/python -m pytest -q tests/test_ncert_pilot.py
```

The builder verifies pinned PDF hashes and refuses to overwrite different frozen outputs. `--download` retrieves missing official PDFs but refuses a changed edition. The local `pdftotext` version is recorded; a version producing different text requires an explicitly separate dataset version. Two focused tests pass, including page-break headings, solution boundaries, and immutable outputs.

**Status:** source preparation and target extraction review complete. Earlier-context QA and independent educational labels remain pending. No NCERT model inference, claimed accuracy result, Lean proof, full-book audit, or submission occurred. The 72 synthetic held-out cases remain untouched.
