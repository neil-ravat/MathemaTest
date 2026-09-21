# MathemaTest local research status — 18 September 2026

The local retrieval and model pilot runs on this Mac. This is a development foundation, not a reproduced paper or a submission-ready result. All work remains local; no pushes, pull requests, or paid model calls were made. Existing manuscript packages remain untouched.

The subsequent controlled technical study is documented in [CONTROLLED_STUDY.md](CONTROLLED_STUDY.md). It adds a frozen 120-case synthetic benchmark, evidence-aware outputs, five retrieval methods, and an enforced held-out gate. Both local models scored 4/7 on the revised-prompt gate, so the held-out evaluation remains closed. These constructed cases do not replace the missing original experiment records or establish human-validated educational judgments.

## What was recovered

Upstream: `VedantShirgaonkar/Causal-Neuro-Symbolic-GraphRAG-for-Automated-Auditing`, commit `601c4fa333de77b23e00208b3059a5f86b974266`. The clone has full available history (7 commits), 108 tracked files at that revision, main as its only remote branch, and no tags. No submodule or LFS payload was found. Local changes are uncommitted on main.

| Asset | Available evidence | Limit |
|---|---|---|
| Python pipeline | `src/`, `scripts/`, tests | Original graph workflow requires Neo4j and a populated database |
| Original reports and plots | `docs/`, `assets_readme/` | Stored summaries and graphics do not establish reproducibility |
| Lean project | `mathematest/` and its pinned dependency manifest | Mathlib dependencies are not installed locally |
| Original textbook dataset | Missing ignored `data/` | Not found in available Git history |
| Original raw experiment output | Missing ignored `artifacts/` | The 503-case audit and 30-case benchmark cannot be reconstructed from summaries alone |
| Original database state | No Neo4j export recovered | Must be rebuilt or supplied by teammate |
| New public corpus | `data/openstax_calculus_v1/` | A new dataset, not the missing original experiment |

The original settings use GPT-4o-mini for generation and audit operations; code and reports also mention GPT-4o. Sentence-transformer embeddings run locally. The local runner explicitly selects Ollama and allows only a loopback endpoint. Do not run the historical benchmark expecting an offline program: it initializes cloud clients and has additional experimental-design problems.

## New corpus and local runs

`scripts/prepare_openstax.py` downloads the official [OpenStax calculus source](https://github.com/openstax/osbooks-calculus-bundle) at revision `8dbc2ce19e804924b2517b89ac72ee45be949d15`. It preserves source files, hashes, ordering, attribution, and MathML. Source license: CC BY-NC-SA 4.0. There are 55 modules and 5,283 extracted records. Unsupported math markup is flagged in 300 records; images are not downloaded. These exclusions must be reported in any study. Text rendering is not a substitute for checking the original formula.

The textbook pilot indexed 1,978 short, supported passages. Its three arms use the same model, prompt, and maximum four retrieved passages: no retrieval, unrestricted vector retrieval, and vector retrieval restricted to earlier positions in the same source. The target itself is excluded. This is not the full GraphRAG method. Positional filtering does not remove pretrained model knowledge, and retrieval failure is not proof of a textbook omission.

| Saved run under `artifacts/local_pilot/` | Model | Calls | Observed outcome |
|---|---|---:|---|
| `20260917T193450048510Z-fixtures` | qwen2.5-coder:7b | 21 | Expected fixture verdicts matched 0/7, 1/7, 1/7 across the three arms |
| `20260917T193712020146Z-fixtures` | mistral:latest | 21 | Expected fixture verdicts matched 0/7 in each arm |
| `20260917T195052982005Z-textbook` | mistral:latest | 18 | 17 abstentions and 1 invalid structured response; no independent labels |

The seven fixtures are author-constructed engineering checks. Their results expose failures; they are not accuracy estimates on educational data. All failures are retained. Each run stores cases, prompts, contexts, responses, timings, model identity, and a manifest. The later textbook manifest also records individual source-code hashes. Unrestricted retrieval contained future passages in every retrieved case; the position-filtered arm contained none in these runs. This verifies the boundary behavior, not educational value.

## Corrections and checks

- Centralized the model endpoint configuration so existing components can use a local OpenAI-compatible server.
- Replaced permissive verdict interpretation with a typed JSON contract and explicit abstention. Corrected legacy keyword scoring that inverted negation or scored an API error as a gap.
- Removed simulated Lean compilation. Missing Lean now reports a toolchain error. `sorry`, `admit`, and new `axiom` declarations cannot count as successful proofs under the conservative text check.
- Successful compilation is marked `COMPILED_UNREVIEWED`: theorem fidelity and axiom dependencies need separate review. Existing `VERIFIED_LOGIC` status remains for compatibility but means only an LLM judgment. It must never be reported as formal verification.
- Installed real Lean 4.26.0 for Apple Silicon under `.tools/`. Two known core-Lean examples compiled and reported no axioms; a false equality failed, and unfinished/custom-axiom proofs were excluded. Evidence: `artifacts/local_lean_checks.json`. No textbook theorem was formally verified in this pilot.
- 79 selected offline regression tests passed. Tests requiring live Neo4j/cloud services were not run. HTML structure and internal links were checked for the 57-page reviewer packet. Automated browser preview timed out, so interactive export and visual layout remain unverified.

## Run on this laptop

From this directory with Ollama running:

```sh
export HF_HOME="$PWD/.cache/huggingface"
export TOKENIZERS_PARALLELISM=false
.venv/bin/python scripts/prepare_openstax.py
.venv/bin/python scripts/run_local_pilot.py --dataset fixtures --model mistral:latest
.venv/bin/python scripts/run_local_pilot.py --dataset textbook --model mistral:latest --limit 6
.venv/bin/python scripts/check_lean_locally.py
.venv/bin/python scripts/make_review_packet.py
.venv/bin/python -m pytest -q tests/test_latex_normalizer.py tests/test_ocr_utils.py tests/test_integration.py tests/test_research_integrity.py
```

The environment uses Python 3.12; `requirements-local.lock.txt` records installed versions. Cached embeddings and model weights are local, outside Git. The Lean smoke script currently uses this Mac's local binary path. The initial source/model downloads require network access; inference uses Ollama. The full original OCR → Neo4j → GraphRAG → Mathlib path is still unvalidated.

## Faculty review

Update: human reviewers are not currently available. At the user's request, two AI agents named Pikachu and Charmender are reviewing the development examples separately. Their outputs are stored under `artifacts/ai_review/` with explicit AI provenance. This provides development feedback only; it does not complete the independent teacher-validation requirement or establish ground truth.

Share `artifacts/MathemaTest_Faculty_Review.zip` with two mathematics teachers. Extract the entire archive and open `faculty_review/review.html`. Both reviewers receive the same 55 source-linked examples without model predictions. The packet includes the rubric, earlier-section navigation, attribution, and an offline JSON export. Images are omitted and uncertainty is an allowed judgment. Export before closing; the page does not autosave.

Use the first five cases for rubric calibration, then preserve independent labels for the remaining cases before adjudication. Ask for a prerequisite and source location in each rationale. These are development examples; reserve disjoint sections or another textbook for final testing. Annotation categories distinguish substantive gaps, adequate material, reasonable background, intentional previews, mathematical errors, and uncertainty. They are not automatically interchangeable with model verdicts: agree on the mapping before evaluation.

## Research priorities before rewriting results

1. **Establish trustworthy labels.** Collect independent reviews, record disagreements before adjudication, and document the intended student background. Expand sampling to exercises and context-dependent cases after checking extraction. Report class support and agreement; do not manufacture gap examples to imply natural prevalence.
2. **Repair model behavior on development data.** Examine contradictory arithmetic judgments and excessive abstention. Separate explicit prerequisite identification from adequacy judgment, and require cited evidence. Compare changes on all existing development cases; retain earlier runs. Do not tune against the final test set.
3. **Rebuild and validate the graph.** Import source-order nodes and explicit source references; do not call ordinary citations validated prerequisite edges. Independently audit inferred edges. Apply the same position boundary to every graph expansion and reranking step.
4. **Freeze a matched evaluation.** Compare no retrieval, vector retrieval, position-filtered vector retrieval, and validated graph retrieval with matched models, prompts, and token budgets. Add lexical retrieval and graph ablations. Lock held-out cases before tuning, group splits by section/book, and include valid examples, assumed knowledge, deliberate previews, and genuine gaps. Use paired uncertainty estimates, class-wise precision/recall, abstention coverage, evidence support, latency, and errors in denominators. Choose sample size from pilot uncertainty, not a desired significance result.
5. **Limit formal claims.** Review the generated theorem against the actual textbook statement; record compiler/toolchain/dependency hashes, extracted theorem type, and `#print axioms` output. Compile success alone cannot show curriculum adequacy. Report failures, admissions, and unavailable toolchains separately.
6. **Audit every manuscript number.** Map tables/figures to exact case IDs and raw outputs. The 503-case, 30-case, cross-textbook, and inherited formal-verification claims remain unverified. Historical NCERT chapter subtotals and percentage calculations need reconciliation. The historical graph-path count is not a measured recall improvement. Reproduce each claim on the new protocol or remove it.
7. **Then revise the paper.** Position the contribution as curriculum-constrained retrieval for prerequisite auditing. Avoid causal-inference and learning-effectiveness claims without the corresponding study. Retain negative findings and compare against related work before claiming novelty. Agree authorship and confirm previous submission destinations with the team.

## Journal choice and submission preparation

These are scope-based candidates, not predictions of acceptance. Official pages checked 18 September 2026.

| Priority | Journal | Evidence needed for this project |
|---|---|---|
| Primary | [International Journal of Artificial Intelligence in Education](https://link.springer.com/journal/40593/aims-and-scope) | Educationally meaningful knowledge representation and independently evaluated auditing |
| Alternative | [Education and Information Technologies](https://link.springer.com/journal/10639/aims-and-scope) | Rigorous educational technology study with practical curriculum-review value |
| Conditional | [Applied Intelligence](https://link.springer.com/journal/10489/aims-and-scope) | Demonstrable methodological innovation beyond applying existing tools to another dataset |

IJAIED offers a subscription route, which avoids choosing the optional open-access APC; its [publishing page](https://link.springer.com/journal/40593/how-to-publish-with-us) refers fee questions to the publisher. Zero mandatory charges therefore remains to be confirmed before submission. Do not select a paid option by default. Check the alternatives' current [EAIT](https://link.springer.com/journal/10639/how-to-publish-with-us) and [Applied Intelligence](https://link.springer.com/journal/10489/how-to-publish-with-us) fee pages when considering them.

IJAIED preparation checklist, based on its [author guidelines](https://link.springer.com/journal/40593/submission-guidelines):

- [ ] Replace the customized Science Publications class with the recommended Springer template; mathematical manuscripts may use LaTeX.
- [ ] Abstract of 150–250 words; 4–6 keywords.
- [ ] Author–year citations and an alphabetized reference list; include available DOI links.
- [ ] Complete editable sources and title-page author/contact information.
- [ ] Funding, competing interests, author contributions, and a data-availability statement matching what can actually be shared.
- [ ] Document substantive LLM use in the methods and retain human author accountability.
- [ ] Resolve source permissions/attribution and institutional requirements for the planned teacher study.
- [ ] All authors approve the final submission; confirm it is not under review elsewhere.
- [ ] Recheck current portal instructions, review anonymization requirements, and fees. Do not assume the former JMP package meets IJAIED requirements.

Publication readiness requires the remaining evidence above. The next decision should follow faculty judgments and model diagnostics, rather than another immediate submission of the existing results.
