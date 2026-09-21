# Matched NCERT development baseline harness

`scripts/run_ncert_baselines.py` runs direct-model, vector-only and factual-graph-assisted answers against an explicit existing corpus. No inference was performed when preparing this harness. Twenty-two focused tests pass.

Run one inspected development case first:

```sh
.venv/bin/python scripts/run_ncert_baselines.py \
  --input-run artifacts/ncert_connected_smoke/20260920T134850055778Z \
  --case jesc111:example-11.1
```

Omit `--case` to attempt all twelve development examples (36 arm attempts). A graph extraction failure yields a graph-arm error, not a substituted curated graph. Preflight service failures stop before inference. Use a newer automatically extracted input run when available; the example command uses the historical successful run, whose graph has known quality problems.

All arms share the question, background, answer schema, model, seed, temperature and output-token limit. Native Ollama `/api/chat` fixes a 16,384-token context window and 1,500-token generation maximum. The retrieval arms share an index containing native paragraphs **and automatic entity excerpts**, so the vector arm is a graph-enriched corpus baseline rather than pure paragraph RAG. Both start with the identical eight cached vector candidates. The graph arm additionally follows one hop of incident factual relationships in either direction, preserving each edge's true direction in provenance. Allowed types are MEASURES, FLOWS_THROUGH, CONTROLS, EXPRESSES, USES_QUANTITY, HAS_UNIT and DERIVED_FROM. Endpoint roles, source IDs, offsets and original text are checked for seed node, edge and neighbor. Only original neighbor and edge excerpts are added, never model-written relation descriptions.

Both retrieval arms deduplicate identical source spans, use the same cross-encoder and keep at most four whole passages/6,000 characters. Global factual discovery, unique selected logical paths and novel context beyond the vector seeds are distinct recorded quantities. Identical final contexts are reported explicitly. There is no educational prerequisite traversal in this ablation and no prerequisite-benefit claim. The production retrieval implementation is unchanged.

Direct answers may use learned subject knowledge and have no source passages or source-support score. It is a secondary answer baseline. The primary comparison is graph versus vector. The common response schema handles roots, classification and multipart answers; optional arithmetic checks establish numerical-expression consistency, not problem-solving validity or Lean proofs.

Outputs in `artifacts/ncert_baselines/<timestamp>` preserve source code, input configuration, source namespaces, graph snapshot, reranker revision, Ollama model digests, exact requests, raw HTTP responses, parsed responses, usage and timing. There are no model retries. Arm order rotates deterministically by case. The vector search is performed once and cached for both retrieval arms; its measured duration is reported separately and added to each arm's comparable latency, distinct from observed per-arm wall time. Reranking and factual augmentation durations are recorded. A stopped run retains completed results and its last pending request.

Scoring reads the existing AI-authored reference only after predictions. Automatic scoring is deliberately restricted to scalar numerical reference agreement for Electricity 11.1, 11.2, 11.4 and 11.6, with errors and abstentions retained in the denominator. This omits units, conditions, reasoning and source support. All broader correctness judgments remain unscored pending separate review. Any later agent review is AI-reviewed agreement, not independent expert ground truth.

Wilson intervals are descriptive for this small convenience sample; the cases are clustered, development-exposed and not a random population sample. No educational accuracy, generalization or graph superiority is asserted. Local hardware/electricity cost is unmeasured; recorded per-arm latency excludes graph extraction and setup costs, so it is not total system cost.

## Fresh operational feasibility

Build a new isolated corpus, then pass its printed path to the baseline runner:

```sh
.venv/bin/python scripts/build_ncert_study_corpus.py \
  --cases-file data/ncert_fresh_reservation_v1/fresh_candidates.json
.venv/bin/python scripts/run_ncert_baselines.py \
  --input-run artifacts/ncert_study_corpus/REPLACE_WITH_PRINTED_RUN \
  --cases-file data/ncert_fresh_reservation_v1/fresh_candidates.json
```

The builder freezes code and construction settings before inference. It ingests the source PDFs, verifies hashes and question boundaries, builds the common native-text index, and calls the staged extractor once per source on the prefix ending at the last selected target. This construction can see earlier selected targets and solutions; query-time evidence remains independently restricted to original spans ending before the specific target. A source prefix exceeding 48,000 characters produces an explicit graph error without truncation. Each source is marked `success`, `error` or `empty`; failed/empty sources produce graph-arm errors while other arms can proceed.

Nondevelopment case files have no default reference file and remain unscored after prediction. `--references-file` is optional; new case IDs never acquire automatic scalar scores through the four-case development scorer. A separate postprediction AI review must remain labeled as such. The fresh convenience subset is an operational feasibility exercise, not the proposed larger research evaluation.
