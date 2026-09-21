# NCERT comparative pilot protocol v1

Design declared 20 September 2026. This is a frozen design proposal and development-run specification, not an external preregistration or completed fresh evaluation. Configuration/corpus hashes must be locked before fresh inference. Revisions require a new version and retain failed earlier runs.

## Claims and tasks

Primary question: does automatic graph-assisted retrieval improve fully correct, source-supported answers relative to vector retrieval under matched budgets? Secondary: answer agreement versus a direct model; prerequisite evidence quality; operational cost/failures. Numerical arithmetic verification alone does not verify source interpretation, units or educational necessity.

The user selected **agent-only checking**. Reference labels will be two separately authored AI reviews plus recorded adjudication against pinned sources; label every result **AI-reviewed reference agreement, not independent expert accuracy**. Agreement among agents may share model biases and is not educational validation. Human expertise is optional future validation, not a blocker to this exploratory work. No claim of true textbook-defect prevalence or learning improvement is supported by this design.

## Splits and acquisition

All previously inspected NCERT chapters (jemh104 and jesc111), their 12 examples, their earlier context and every current curated graph are development only. The existing 72 synthetic reserved cases remain outside this study and must not be opened. No random split within these exposed chapters counts as fresh evidence.

Reserve six new official chapter files by identifier before reading their bodies: mathematics jemh103, jemh105, jemh106 and science jesc109, jesc110, jesc112. These are a source reservation, not 60 already selected/eligible cases. Verify titles/edition from front matter, hash original bytes, retain download failures rather than substitute favorable chapters. Some physics chapters may lack ten eligible questions; inventory availability without inspecting answers and report the shortfall or declare another version before selection. Freeze candidate IDs and selection seed 42 before labels/inference. Never mine failures or answer difficulty to select cases.

Intended pilot: 60 target families, 30 per subject, ten per source chapter, sampled uniformly without replacement from a pre-enumerated pool of worked examples and numbered exercise questions (a multipart question is one family). Exclude target duplicates and near-duplicate numeric variants as one family before sampling; record all exclusions and reasons. Include diagram/symbolic problems in the inventory even if unsupported; report unsupported coverage rather than silently selecting only arithmetic. Eligibility requires a recoverable question/solution boundary, source-order metadata and source image available for AI transcription QA. Do not inspect reference answers to decide eligibility. If fewer than 60 eligible families exist, report the reduced feasibility pilot and avoid invented cases or post-outcome replacement.

Sixty is a workload-limited exploratory target, **not a power calculation**. Under independent Bernoulli assumptions, worst-case standard error is about 0.065 at n = 60 (roughly ±0.13 for a normal 95% interval); shared chapters/families reduce effective information. This pilot cannot reliably detect small improvements. A later confirmatory sample size must use a prespecified worthwhile effect and pilot paired discordance/cluster dependence, not whichever effect looks favorable.

## Matched arms

Run direct, vector and graph for every selected family with one pinned local model and identical question, declared background, answer schema, seed 42, temperature0 and output limit 1500. Pin actual Ollama weight digest, not just a tag. Execution order rotates deterministically by case index across the three arms to distribute order effects; no corrective retries. Direct gets no external passages and may answer from internal knowledge. Citation availability is `SOURCE_UNAVAILABLE` for direct; its empty citations are not automatically factual errors. Direct is a secondary answer-only comparator, not an identical evidence task.

Vector and graph use the same native-PDF index, source-order cutoff, embedding model, reranker and evidence budget: eight vector candidates, at most four whole passages and 6000 characters after reranking. Do not split a cited passage while retaining its old offsets. Record actual prompt tokens since character budgets are not token equality. Graph adds only automatically accepted incoming prerequisite expansions; use exactly the same ranking/truncation policy. Curated graph runs are a separately labeled oracle-like development diagnostic and cannot establish automatic performance. Record graph rejection/empty graph; no silent replacement with hand corrections. A prespecified vector fallback is allowed only as a named system policy and its rate must be reported.

All retained passages and every traversed graph node/edge must predate the target and match permitted source/background. Building a whole-chapter graph must not allow later material to alter an earlier node or relationship; preferably construct from admissible prefixes, or enforce evidence-position predicates on edges as well as nodes. Target solutions and future evidence are excluded. Preserve exact payloads and path provenance.

Primary graph-versus-vector isolates the contribution of graph expansion only when other components and context budgets match. The direct comparison changes evidence availability. An optional `graph_without_prerequisite_expansion` arm is redundant with vector unless implementation differences exist; document those before adding it. Separate automatic-graph versus curated-graph diagnostic tests extraction quality, not the production method.

## Reference review and freezing

AI reviewers A and B receive original questions, prefix sources and official solutions but no evaluated-model predictions or each other's answers. They record solution consultation and previous exposure. Each produces answers for all subparts, acceptable equivalences/tolerances, units, prerequisites and exact source support. A third adjudication pass resolves disagreement with evidence; preserve both initial judgments. Unresolved questions remain `UNCERTAIN_REFERENCE`, never relabeled to match predictions. For development, reviewerA has seen historical candidate notes; disclose this contamination. No AI rubric field may say independent expert or human-validated.

Before fresh inference, lock source hashes, candidate IDs, transcriptions, allowed-background corpus, reference-review hashes, unresolved flags, complete graph pipeline/prompt/schema versions, model/embedding/reranker digests, scoring rules and runner hash. Reference labels live outside model payloads and graph construction. The reservation file alone is not a completed evaluation lock. Automatic graph extraction reliability is measured on all attempted source units, not only saved graphs.

## Outcomes and denominators

Primary retrieval-arm score is all-subparts answer-and-unit correctness **and** adequate source support relative to adjudicated AI reference. Report answer correctness separately for all three arms; report citation validity (real/source-order admissible), semantic support, required-prerequisite recall and graph-edge precision/direction separately. A matching final number cannot substitute for units/derivation. Exact arithmetic/Lean results are separate engineering checks. For citations/edges, score against source pages and reference review, not the system's own graph. Source absence in incomplete curriculum becomes uncertainty, never a proven gap.

Denominator is every scheduled family. Count runtime errors, extraction failures, malformed/truncated outputs and unsupported inputs as non-success in full-set operational success. Record abstentions distinctly. Report resolved-reference agreement only over prespecified resolvable cases, alongside unresolved fraction and full-set lower/upper success bounds; never make uncertain cases disappear. Report accepted-answer coverage and conditional agreement; at zero coverage conditional agreement is undefined.

Publish paired graph-minus-vector differences and gains/losses on identical families. Use seed 42, 10000 chapter-cluster bootstrap resamples for descriptive 95% percentile intervals and show per-chapter results; with only six chapters, intervals are unstable and do not justify broad claims. Include family-level paired discordance table; any significance test is exploratory, secondary and labeled as such. No selection of favorable model/subject/subpart/retry. If all graphs have zero prerequisite expansions, report no exercised graph benefit rather than a positive graph evaluation.

Report wall-clock latency per stage, calls, input/output tokens, peak memory if measured, graph construction amortized and unamortized, and failures. Local compute has zero billed API spend, not zero resource cost; do not invent energy/dollar estimates. Publish model/hardware/runtime versions and whether caches were warm.

## Stop and release rules

Complete scheduled cases unless resource failure prevents it; preserve every attempt and incomplete status. No retuning midway. A software bug triggers a separately versioned engineering rerun with the old run retained. Do not promote exposed fresh cases back to held-out status after debugging. A run earns a research report only with an honest scope statement; positive results are not a completion criterion. Fresh benchmark outcomes and expert validation are currently uncompleted.
