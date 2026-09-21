# Evidence and calculation study — 20 September 2026

Completed the three requested tasks: diagnose prior failures, implement one focused intervention, and compare it on every development case. Three agents worked on diagnosis, implementation, and reporting in parallel; inference began after integration and protocol freeze.

The new pipeline asks for structured prerequisite evidence and an expanded integer expression, checks that expression with a bounded calculator, and selects the verdict deterministically. It does not formally verify the model's substitutions or establish textbook defects.

## Results

| Model | Original prompt | Earlier evidence prompt | Calculator-assisted method | New fixture score |
|---|---:|---:|---:|---:|
| Qwen 2.5 Coder 7B | 17/48 | 13/48 | 29/48 | 4/7 |
| Mistral | 17/48 | 8/48 | 16/48 | 2/7 |

The always-PASS baseline is 24/48. All 48 cases were attempted for each model; six Qwen errors and thirteen Mistral errors remain in the denominators. These development results do not show a consistent improvement over the original prompt across models. Family-bootstrap intervals and detailed metrics are in the [comparison report](artifacts/controlled_study/decomposed_comparison_20260920/RESULTS.md).

Each model also produced four correct false-equality verdicts with demonstrably wrong calculated values. Correct labels therefore cannot be treated as sound mathematical derivations. The [evidence review](docs/decomposed_evidence_review.md) distinguishes calculation agreement, unsupported substitutions, and validation failures. Of accepted numerical calculations, only 11/28 for Qwen and 6/29 for Mistral agreed numerically with the supplied definitions; even numerical agreement does not prove faithful derivation.

Both fixture gates failed. All 72 held-out cases remain unevaluated. The new runner cannot execute or authorize held-out inference.

## Checks and artifacts

- 110 new local inference calls: 96 development and 14 fixtures. No correction retries, training, paid calls, or remote publication.
- 100 offline regression and experiment tests passed. Historical output hashes, all 48 labels, and all 192 historical development payloads were independently checked.
- Completed development run: `artifacts/controlled_study/20260919T223749942686Z`.
- Completed fixture run: `artifacts/controlled_study/20260919T225703610993Z`.
- Both runs have identical source snapshot hashes, prompts, and recorded local model digests. Prediction hashes, successful raw-output decoding, arithmetic decisions, and matched cases were verified. Historical baselines lack weight digests, so their identical weight identity cannot be proven.
- [Failure diagnosis](docs/development_failure_diagnosis.md) and [protocol declared before inference](docs/decomposed_protocol.md). The development run also retains a copy of that protocol.

The 48 cases contain 40 unique admissible inputs across eight dependency families; missing/future pairs are identical after filtering. This is a narrow synthetic, exploratory comparison informed by development failures, not independent educational validation.

## Reproduction

From this repository, using the existing virtual environment and local Ollama:

```sh
.venv/bin/python scripts/audit_development_labels.py
.venv/bin/python scripts/run_decomposed_study.py --phase development
.venv/bin/python scripts/run_decomposed_study.py --phase gate
```

Each inference invocation creates a new append-only run. Preserve the completed runs above. To reproduce the comparison without new model calls, choose an unused report output directory:

```sh
.venv/bin/python scripts/report_decomposed_study.py --baseline artifacts/controlled_study/20260917T201622567827Z --revised artifacts/controlled_study/20260919T223749942686Z --output artifacts/controlled_study/decomposed_comparison_recheck
```

The next proposed experiment should check model-extracted dependencies and substitution steps against source definitions before accepting a calculation. Declare it as a new protocol and compare against this one; do not repair these outputs retroactively. A deterministic evaluator for this narrow grammar can serve as a transparent baseline, but success on that grammar would not establish general textbook understanding. No further intervention has been run.
