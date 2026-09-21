# Source-grounded filtering results — 20 September 2026

The new checker caught every wrong asserted verdict in the saved synthetic development responses, but retained too few answers to establish a useful model-based auditor. A separate rules-only evaluator solved the entire narrow grammar, so these cases do not demonstrate that a language model adds value.

## Completed experiment

Replayed all 96 saved development responses and all 14 saved fixture responses through a new source checker. No new model calls, training, prompt changes, or correction retries were made. Original responses and scores remain intact. The 72 held-out cases remain unevaluated.

The checker follows definitions from the supplied earlier passages and background, derives dependencies and an expanded expression, then checks the model's missing-definition list, citations, and substitution structure. It accepts the original answer or withholds it as ABSTAIN; it never replaces the answer with the source evaluator's result. Historical errors remain errors.

| Model | Original correct / 48 | Accepted / 48 | Correct among accepted | Wrong verdicts withheld | Correct labels withheld |
|---|---:|---:|---:|---:|---:|
| Qwen | 29 | 22 (45.8%) | 22/22 | 13 | 7 |
| Mistral | 16 | 11 (22.9%) | 11/11 | 19 | 5 |

Full-set correct counts fall to 22/48 and 11/48. Accepted-only accuracy must not be presented as full-dataset accuracy. Six Qwen and thirteen Mistral historical development errors remain in those denominators. The source checker also rejects some valid simplifications because its structural equivalence rule is deliberately conservative.

Independent review traced the correct-but-withheld results: Qwen's seven comprise four wrong calculations with lucky correct labels and three valid algebraic rewrites outside the matching rule. Mistral's five comprise four wrong calculations with lucky correct labels and one correct calculation missing a required citation. The 33 accepted outputs comprise 13 checked numeric calculations, six genuine missing-definition findings, and 14 previews across the two models.

Among actual gap cases, the guarded models retain only 6/16 correct Qwen findings and 0/16 Mistral findings. Accepted outputs also include previews: 8 for Qwen and 6 for Mistral. The small accepted subset therefore does not establish broad mathematical or prerequisite competence.

The fixture replay stays at 4/7 for Qwen and 2/7 for Mistral. Neither meets the reliability requirement. This offline replay is not a fresh inference gate and cannot authorize held-out evaluation.

## What the deterministic baseline tells us

The source evaluator alone obtains 48/48 development labels and 7/7 fixture labels using visible text, without model predictions or benchmark oracle fields. It is an interpreter designed for this constructed integer-function grammar after development inspection. This establishes a useful baseline and exposes the benchmark's limited scope; it is not a novel general AI result or evidence about real textbook defects.

The next research step should move from tuning familiar synthetic prompts to evaluating extraction of definitions and prerequisites from realistic mathematical passages, with independently checked evidence. Keep the source interpreter as a transparent baseline. Broader claims require source extraction validation, appropriate background assumptions, and independent educational labels; those have not been established here. No further experiment was run in this phase.

## Validation and reproduction

- 147 offline tests passed, including 30 independently authored adversarial checks.
- Verified all 110 input records, original raw-output decisions and errors, matched case sets, saved-run hashes, and model/source provenance.
- Verified output hashes and source snapshots; all 33 accepted development outputs have correct labels on these cases. This observed result is not a guarantee of correctness on unseen input.
- The grammar covers limited integer arithmetic, explicit definitions, and narrowly phrased previews/background. Unsupported text, cycles, ambiguous definitions, or parser limits abstain. Metadata such as passage ordering and context completeness is trusted.
- Expression matching allows associative regrouping of addition/multiplication, preserving order and literals. It rejects commutative reordering, constant folding, and other valid rewrites outside that rule. It checks structured evidence, not the truth of arbitrary explanatory prose.
- There are eight development families and 40 distinct public inputs among 48 cases; duplicate missing/future inputs and development-informed design limit generalization claims.

Run the offline replay from this repository, choosing a new output directory:

```sh
.venv/bin/python scripts/replay_source_guard.py --development artifacts/controlled_study/20260919T223749942686Z --gate artifacts/controlled_study/20260919T225703610993Z --output artifacts/controlled_study/source_guard_replay_recheck
```

[Detailed results](artifacts/controlled_study/source_guard_replay_20260920/RESULTS.md) · [Declared protocol](docs/source_guard_protocol.md) · [Independent review](docs/source_guard_review.md) · [Previous experiment](DECOMPOSED_STUDY.md)
