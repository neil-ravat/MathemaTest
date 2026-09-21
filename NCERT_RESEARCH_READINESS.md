# NCERT research-readiness work

Status: the frozen exploratory round, reference reviews, output scoring and graph audit are complete. See [NCERT_FRESH_STUDY_RESULTS.md](NCERT_FRESH_STUDY_RESULTS.md) for adjudicated results: 0 complete answers across 30 attempts; automatic graph semantics remain unreliable. The user selected agent-only checks; every reference and semantic audit is AI-reviewed, not independent expert ground truth.

## What has been implemented

- Staged automatic extraction separates entity discovery, role-constrained factual-edge selection and a second local model's source-support review. Invalid or unsupported proposals are retained in audit artifacts and excluded from the stored graph. A narrow explicit unit-prose guard rejects quantity/unit mismatches. This is an engineering intervention, not established extraction reliability.
- Source order is checked on graph edges as well as nodes. A real Neo4j regression probe rejects future, cross-source and malformed edge provenance even when both endpoint nodes precede the question.
- Twelve exposed development examples have two separate AI reference passes and adjudication. Fresh predictions were frozen before separate reference passes, with model-answer text withheld from both reference reviewers; all ten references were adjudicated.
- The new comparison uses direct answering, vector retrieval and one-hop factual-graph augmentation. Vector and graph share an automatically graph-enriched index, eight vector seeds, reranker, four-passage/6000-character context limit and the same answer model/settings. This isolates edge expansion; it is not a pure raw-paragraph versus entire graph-system comparison. The runner evaluates answer/support feasibility, not the complete curriculum auditor, MCQ generator or Lean formalization pipeline.
- Ten fresh worked-example families were selected by a predeclared first-two-per-chapter rule: six maths and four science across five contributing chapters. A sixth reserved chapter yielded no matching examples and was not replaced. This is a convenience feasibility subset, not the proposed 60-family study or a powered sample.
- Exact inputs, source/model/configuration versions, requests, responses, errors, token counts and timing are retained. Errors and abstentions stay in the all-case denominator. Local energy/hardware cost is unmeasured; no zero-cost claim is justified.

## Development evidence

The successful staged development pilot, `artifacts/grounded_graph_pilot/20260920T143137143546Z`, retained 11 nodes and 2 factual edges. It used 3 model calls and 226.83 seconds of model-request wall time. Two earlier failed staged attempts remain available: one call/55.16 seconds and three calls/292.98 seconds. Across these three development attempts, there were 7 calls, not only the final successful run's 3.

The retained edges are electric-current HAS_UNIT ampere and ammeter MEASURES electric-current. The second model endorsed an incorrect current-to-coulomb edge; the deterministic guard rejected it. The same conservative guard also rejected valid milliampere and microampere links because their prose did not match its supported patterns. Missing charge/time/formula entities and entity-role choices restrict graph coverage. Source-localized excerpts do not guarantee full semantic entailment. There are zero accepted educational-prerequisite edges. Jessie’s separate audit found both retained edges supported, seven entity descriptions supported in the original source (three require a visual exponent check), and four descriptions only partly supported by their actual selected excerpts. All 13 retained source spans matched exactly. See `docs/ncert_grounded_development_review.md`.

Final targeted engineering regression suite: 117 passed, 0 failed (one existing Pydantic configuration deprecation warning). These tests cover provenance, schemas, retrieval matching, fresh selection/review packets, native ingestion and arithmetic/audit contracts. They do not measure answer correctness or graph semantic accuracy. See `artifacts/ncert_research_tests_final.txt`.

## Fresh construction outcome

Construction completed before the user-requested pause. It retained 34 model-extracted entities and 9 factual edges: jemh103 9/6, jemh105 6/0 (empty graph), jemh106 5/1, jesc109 validation error, jesc112 14/2. Three of five source chapters produced nonempty graphs. The empty and failed chapters make four of the 30 planned answer arms unavailable under the frozen no-fallback policy. There are no accepted educational prerequisites.

The 13 construction calls consumed 1,910.1 seconds of model-request wall time (31.8 minutes), 66,380 prompt tokens and 8,199 output tokens. These counts include failed/empty construction. The completed semantic audit found 14/34 node descriptions fully supported and 0/9 fully supported edges; node roles remain a separate correctness field. The completed construction is preserved; resuming does not rebuild it.

## Frozen-study qualifications

Graph construction uses each chapter's prefix through the last selected question start. Therefore it can see the first selected question and its solution while selecting graph entities and relationships. Query-time checks exclude later text from supplied evidence, but cannot undo this possible influence on graph selection/topology. The study must not be described as fully target-blind or leakage-free. This issue was identified before outcome inspection; the frozen run is preserved without a silent mid-run method change. Future confirmatory construction should end before the earliest target or build separately for each target.

Other limits: postprediction original-page review found missing AP numerators, an essential missing diagram, flattened fractions and caption contamination; public NCERT examples may have appeared in model training; AI reviewers share model-family/context limitations; complete prior-grade curriculum is unavailable; factual relations are not pedagogical prerequisites. A positive graph-benefit or missing-prerequisite-detection claim is currently unsupported.

## Evidence locations

- `docs/ncert_comparative_protocol_v1.md`: initial design.
- `docs/ncert_fresh_feasibility_amendment_v1.md`: fixed subset rule and prediction-before-reference timing.
- `docs/ncert_factual_graph_amendment_v1.md`: actual factual-edge ablation.
- `docs/ncert_fresh_execution_amendment_v1.md`: pre-execution context/time limits and code/config lock.
- `docs/ncert_ai_scoring_rubric_v1.md`: AI reference/output/complete retained-graph scoring rules; frozen before prediction inspection.
- `artifacts/ncert_expert_review_v1/`: exposed development reference packet and completed AI annotations.
- `artifacts/ncert_study_corpus/20260920T144038507430Z/`: fresh automatic construction, including every failure.

Fresh answer, support and graph-audit results are complete in the linked study report. They do not support a paper-ready effectiveness claim.

## Completed execution sequence

1. Ran all 30 baseline arm attempts and froze prediction artifact hashes before reference inspection.
2. Completed separate AI reference annotations by Weezing and root (substituting for unavailable Jessie), then hashed and adjudicated them. Model predictions were withheld during reference review.
3. Arbok and root audited every retained automatic graph claim without repairing the evaluated graph.
4. Completed two separate scoring passes on the shuffled arm-blinded output packet, preserved disagreements and adjudicated them.
5. Generated all-case answer/support counts, chapter-paired uncertainty, failure and cost summaries. The evaluated cases were not tuned or rerun in response to outcomes.
6. Final integrity verification matched all 189 locked entries; final report review found no material corrections.
