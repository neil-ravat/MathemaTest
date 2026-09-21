# MathemaTest NCERT integration check

**Outcome: blocked before LLM auditing. Zero complete PDF-to-audit cases.** The existing system cannot currently complete a valid end-to-end NCERT benchmark in this environment. This is a failed integration check, not a zero-accuracy result.

The check used real production classes and isolated storage. No mock OCR, graph, embedding, retrieval or compiler components were substituted. It made zero LLM calls, changed no production modules and preserved all fifteen original NCERT source-package files. The earlier Qwen 5/12 and Mistral 3/12 direct-model answer counts remain separate baseline results.

## Executed checks

| Stage | Actual test | Outcome |
|---|---|---|
| PDF ingestion | `IngestionEngine.process_pdf` on Maths PDF page 3 and Science PDF page 2 | Both fail layout extraction because `doclayout_yolo` is absent; no structured blocks produced. `unimernet` is also absent, but this earlier failure prevents reaching formula extraction. |
| Graph service | Real `Neo4jClient` connectivity to local port 7687 | Connection refused. Docker daemon is also unavailable. No graph was populated. |
| Graph extractor | Initialize `GraphConstructorAgent` with the local Ollama endpoint and dummy local token | Disabled by the API-key validator's `sk-` prefix requirement. No extraction call made. |
| Vector index | Real cached MPNet embeddings and Chroma in a new isolated directory | Fifteen previously reviewed NCERT spans indexed successfully. This separately seeded index is **not ingestion output**. |
| Audit retrieval | Real `HybridRetriever.retrieve_for_audit`, twelve targets, top three, reranking disabled for this diagnostic only | Seven contexts contain target or later material. Graph failures are logged and swallowed, leaving vector-only results. No observed cross-source hits in these returned results. |
| Default reranking | Same production audit retrieval with `rerank=True` | Cross-encoder weights unavailable in local cache. The check deliberately used offline mode; no model download was attempted. |
| Lean bridge | Real bundled Lean 4; core arithmetic and Mathlib-import smoke checks | Core arithmetic compiles as `COMPILED_UNREVIEWED`; `Mathlib.Tactic` import fails. Repository Mathlib package directory is absent. Neither probe verifies an NCERT example. |
| LLM audit | Downstream gate | Not called because the connected ingestion/graph/retrieval prerequisites failed. |

The pipeline-check command exited with status 2 to signal blockers. The separate unit check of the source-order diagnostic passed; that does not mean the pipeline passed.

## Reproduced leakage

The source spans carry exact start/end offsets. The diagnostic compared each returned span's end against the target's start, and also checked source identity. The existing retrieval implementation receives only a chapter number, so its `$lte` chapter condition permits later content in the same chapter.

| Target | Example of inadmissible returned material |
|---|---|
| Maths Example 2 | Later root definition and Example 3's worked solution |
| Maths Example 3 | Its own worked solution and later Example 4 |
| Maths Example 4 | Its own worked solution and later Example 5 |
| Maths Example 5 | Its own worked solution |
| Maths Example 6 | Its own worked solution containing the hall dimensions |
| Electricity Example 11.1 | Later Ohm-law and potential-difference passages |
| Electricity Example 11.2 | Later Ohm-law passage |

This 7/12 finding concerns the explicitly seeded fifteen-span engineering probe. It is not leakage prevalence across the books, a result from automatically ingested chapters, or a full hybrid-graph result. Passing contaminated context to a model would invalidate any claimed advantage over the earlier clean-input baseline.

## Additional code findings

These are observations from the current source, separate from runtime outcomes:

- `src/ingestion/ingestion_engine.py` stores non-formula blocks as strings such as `[text block]`. Installing OCR dependencies alone would not recover the prose and tables required for NCERT auditing.
- `HybridRetriever.retrieve_for_audit` calls `search_concepts`, not `get_prerequisites`. The separate general retrieval path has prerequisite expansion, but the audit entry point does not use it.
- Both vector and graph audit searches use chapter `<=` despite comments describing strict earlier-chapter filtering. Merely changing this to `<` would still be wrong for the intended within-chapter learner: valid earlier content in the same chapter must be retained, while the target and later spans must be excluded.
- `AuditorProver` uses a calculus theorem-proof prompt, including a rule to call missing retrieved context a gap. The current twelve NCERT targets are questions, and incomplete retrieval is not proof of a curricular gap.
- Existing ingestion integration tests explicitly use mock components. Their success cannot certify a real PDF-to-graph-to-audit chain.

## Required repair order

1. Implement real prose/table ingestion and reliable formula handling with source positions; validate it on the pinned NCERT pages. A substitute input route must be named and evaluated as a separate configuration.
2. Bring up an isolated real graph service; make local model configuration work for extraction; preserve source and position metadata in nodes and edges.
3. Enforce source identity and complete span boundaries in both retrieval branches, and connect prerequisite traversal to the audit entry point. Treat failed branches as explicit failures rather than silently calling the remaining branch a complete hybrid run.
4. Make reranking and the intended Mathlib toolchain available, while retaining the distinction between compilation, statement fidelity and certified proof.
5. Freeze a common audit task and evaluation rubric for MathemaTest and direct-model baselines, then run the connected workflow. The previous answer-correctness counts cannot be directly compared with `FAIL_GAP`/`PASS` audit verdicts.

No end-to-end performance or improvement claim is supported yet. This check establishes concrete engineering failures to repair first; it does not determine the eventual merit of the approach.

## Reproduce and inspect

```sh
.venv/bin/python -m pytest -q tests/test_ncert_pipeline_check.py
.venv/bin/python scripts/check_ncert_pipeline.py
```

The checker uses only the local model endpoint configuration and local caches, creates fresh isolated Chroma/Lean artifacts, and makes no inference calls. It diagnoses readiness rather than pretending to be a completed textbook benchmark.

- [Full machine-readable report](artifacts/ncert_pipeline_check/20260920T001633721678Z/report.json)
- [Actual retrieval results and source-order flags](artifacts/ncert_pipeline_check/20260920T001633721678Z/retrieval.json)
- [Actual ingestion outputs](artifacts/ncert_pipeline_check/20260920T001633721678Z/ingestion.json)
- [Reproducible checker](scripts/check_ncert_pipeline.py)

The run directory also contains snapshots and hashes of the production source used for this failed baseline.
