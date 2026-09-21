# Controlled technical study

Follow-up completed 20 September 2026: [evidence and calculation study](DECOMPOSED_STUDY.md), with 110 additional local calls. Qwen improved to 29/48 development matches; Mistral scored 16/48. Both new fixture gates failed and held-out inference remains closed. The results below describe the preserved original study.

This study uses constructed integer-function curricula with deterministic labels. It does not measure naturally occurring textbook defects, teaching effectiveness, or expert agreement. The 55 OpenStax review cases and their AI annotations remain separate.

## Reproduce locally

Use the existing Python 3.12 environment from the repository root. Ollama must be running with `qwen2.5-coder:7b` and `mistral:latest` installed. No cloud endpoint is accepted by the runner.

```sh
export HF_HOME="$PWD/.cache/huggingface"
export HF_HUB_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
.venv/bin/python scripts/controlled_benchmark.py
.venv/bin/python scripts/run_controlled_study.py --phase gate
.venv/bin/python scripts/run_controlled_study.py --phase development
.venv/bin/python scripts/audit_controlled_retrieval.py
.venv/bin/python -m pytest -q tests/test_controlled_study.py tests/test_research_integrity.py tests/test_latex_normalizer.py tests/test_ocr_utils.py tests/test_integration.py
```

The generator is idempotent: it refuses to overwrite an existing different benchmark. `data/controlled_curricula_v1/manifest.json` pins both splits before tuning. All six variants from a dependency family stay together. Eight families supply 48 development cases; twelve different complete topologies supply 72 held-out cases. Integer addition, some substructures, and category semantics are shared; this is topology transfer within a narrow synthetic domain, not broad mathematical generalization. Surface phrasing also differs between splits, so topology and wording effects are not separable in this version.

The categories are supported, missing definition, future definition, permitted background, preview, and false equality (20 cases each). The oracle evaluates explicit operations and dependency availability; it never uses LLM votes. Expected verdicts, category names, required-ID lists, and oracle structures are excluded from model payloads and embedding inputs. Public function definitions contain explicit references; graph retrieval does not use gold prerequisite lists. It does not evaluate automatic reference extraction.

## Evaluation behavior

The default development run compares the original and evidence-first prompts using complete earlier context, on both models: 192 calls. The original prompt receives the same additional evidence-output contract as the revised prompt. This is an adapted baseline, not a byte-identical repeat of the previous pilot.

The complete-context diagnostic includes all earlier passages and is exempt from the ranked retrieval budget. The five ranked arms are `none`, `vector`, `position_filtered`, `lexical`, and `graph`. They use at most four whole passages and a 1,600-character ceiling. This is a matched maximum text budget, not identical token counts; exact prompts and token usage are saved. Embeddings reuse the existing MPNet service. Graph traversal uses only admissible explicit reference edges. Future intermediaries cannot expand to earlier nodes.

Outputs extend the existing verdict contract with `cited_passage_ids`. The runner records `context_complete`; it rejects nonexistent, non-retrieved, and future citations. It also rejects a missing-prerequisite verdict when the retrieved subset is incomplete. This conservative rule means top-k retrieval may have to abstain even when a missing prerequisite exists. It does not provide a full-corpus absence certificate. Citation existence checks do not prove that the cited passage supports the explanation, nor can they detect every uncited use of pretrained knowledge.

JSON syntax failures, schema failures, evidence/scope failures, runtime failures, and truncation stay in the denominator. Wrong judgments with complete context are separated from unresolved retrieval/judgment failures. Automatic diagnostics do not claim to distinguish internal arithmetic errors from instruction-following errors perfectly; the saved reasons support manual inspection.

Summaries include per-class precision/recall, per-category counts, abstention coverage, future-context counts, and model-call latency. Approximate 95% exact-match intervals resample whole dependency families (1,000 resamples, seed 42). With only eight development families they are exploratory. Model-call time excludes retrieval preparation. The retrieval-only audit separately reports shared embedding time and ranking time.

## Held-out gate

Both models must classify all seven original engineering fixtures correctly with complete admissible context under the selected prompt. The held-out command verifies the completed gate's prediction hash, evaluation-code hash, benchmark hashes, and advertised model metadata. It requires one prompt and all five arms in the fixed order. An exclusive `HELDOUT_STARTED.json` marker allows only one test attempt, even if interrupted. Do not delete it to rerun unfavorable results; any later study needs a separately declared version.

The command below is for a future passing gate, not the current failed gate:

```sh
.venv/bin/python scripts/run_controlled_study.py --phase heldout --prompts evidence --arms none vector position_filtered lexical graph --gate-run artifacts/controlled_study/PASSING_GATE_DIRECTORY
```

The runner checks file hashes before opening the test phase. Generating and integrity-checking the sealed split are not model evaluation. No held-out prompts are sent unless the gate succeeds.

## Provenance and limitations

Runs use new directories and exclusive output creation. Predictions are flushed after every call; raw responses and invalid outputs remain available. Completed runs carry a prediction SHA-256. Source snapshots and the local dependency lock support reruns. These are append-only by workflow, not filesystem-enforced immutable storage. The first gate's exact source snapshot was captured before a later bookkeeping hardening change; rerunning with current code requires a new gate.

The initial gate scored 4/7 for both models under the revised prompt, versus 2/7 for Qwen and 1/7 for Mistral under the adapted original prompt. It failed. Held-out inference remains prohibited. The complete development comparison scored 13/48 for revised-prompt Qwen and 8/48 for revised-prompt Mistral; the adapted original prompt scored 17/48 for both. All four configurations were below the 24/48 always-PASS baseline. The completed report is [RESULTS.md](artifacts/controlled_study/RESULTS.md), with per-class metrics and paired family-bootstrap estimates in the neighboring `analysis.json`. There were 224 local calls: 192 development, 28 gate, and four separate arithmetic controls. No held-out model calls were made.

The completed records can be analyzed using `scripts/report_controlled_study.py --gate GATE_RUN_DIRECTORY --development DEVELOPMENT_RUN_DIRECTORY --retrieval RETRIEVAL_AUDIT_JSON`. It verifies completion hashes and writes the report with exclusive creation, preserving any earlier report. This report command is specifically for the failed-gate study; it includes paired prompt differences resampled by family.

No training, paid calls, GitHub pushes, manuscript replacement, or submission belongs to this phase. Formal Lean checking remains separate from these model judgments.
