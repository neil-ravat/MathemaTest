# Grounded extractor review — Weezing

Scope: read-only review of `src/graph_store/grounded_extractor.py`, `scripts/run_grounded_graph_pilot.py` and their source/persistence dependencies on20September2026. No new model calls, database mutations or fresh-question inspection. Three existing grounded-extractor tests passed; two additional adversarial checks reproduced the issues below. These findings describe the inspected version; subsequent fixes need separate verification.

## Actionable findings

1. **Case-only entity names can overwrite one another before failure.** `SourceExtraction` treats `Current` and `current` as distinct, but `_generate_node_id` lowercases its entire key. Same-label entities with the same source span therefore map to the same node ID. The pilot's post-write count assertion catches the discrepancy only after Neo4j mutation. Reject names equivalent under the actual identity normalization before persistence (or preserve case in IDs under a separately versioned identity policy). This was reproduced without a database: schema validation accepted both names and generated IDs were identical.
2. **Excerpt span validation does not enforce valid coordinates.** `source_evidence_units` checks only `end-start == len(text)`. A span `[-4,0)` containing four characters is accepted, and noninteger values can also pass arithmetic. Require integer, non-boolean, nonnegative start and strictly greater end before splitting. Current pilot supplies a valid `[0,target_start)` span, so this is a shared-boundary robustness issue, not evidence that this pilot leaked source content.
3. **Future prerequisite traversal must scope edge evidence, not only nodes.** `Neo4jClient.get_prerequisites` checks every path node's source/offsets but no relationship's evidence offsets. Earlier concepts could be connected by a later passage. The new factual extractor deliberately emits no `PREREQUISITE_OF`, so this is not exercised by the current staged run. Add edge provenance checks before an automatic prerequisite-enabled whole-chapter comparison; unknown evidence must fail closed.

## Current strengths and limits

The real runner passes only the original prefix preceding Example11.1 into extraction, verifies pinned PDF and text hashes, validates schema-compliant raw model responses, rejects duplicate or missing review IDs, filters uncertain/unsupported claims, removes edges whose endpoints were rejected, then checks persisted source slices and counts. Extractor and reviewer weights/tags are recorded. Source excerpts, generated candidates, proposed claims and reviewer verdicts are preserved. No unsupported conversion of model agreement into expert gold is present.

Separate models do not provide independent expert truth. Mistral can approve a wrong Qwen claim, and no deterministic semantic entailment checker establishes factual accuracy. Role constraints prevent certain reversed directions but cannot verify which quantity owns which unit. Exact quotes validate provenance, not semantics. Single-excerpt support may reject valid multi-sentence facts, and sentence/paragraph splitting can damage formulas or split a defining condition from a claim. Report acceptance/coverage and source-review errors rather than “reliable graph extraction” from one example.

The candidate relation set has no pedagogical prerequisite relation. `accepted_prerequisites:0` is correctly explicit; this run cannot show prerequisite retrieval benefit. Factual-graph acceptance is a separate engineering result from the paper's educational prerequisite objective. An empty accepted graph is a possible successful execution and must be reported as zero coverage, not extraction success in a research denominator.

Neo4j persistence uses multiple writes rather than one transaction. A failure can leave partial nodes in a unique failed-run namespace. Preserve that evidence, but downstream studies must reject failed/incomplete inputs or explicitly record fallback; a source-ID name check alone is not sufficient provenance enforcement. The pilot's saved extraction and post-write assertions improve traceability but do not roll back writes.

The source snapshot includes four direct graph files but not all invoked ingestion/config/API-helper code. For exact reproduction, include hashes or snapshots of the transitive code, relevant packages, and the protocol alongside the actual requests/responses. This is a provenance limitation rather than grounds to discard the currently preserved development run.

## Evaluation interpretation

Use `MODEL_CHECKED_NOT_GOLD` throughout. Count all extraction attempts, malformed calls, rejected/empty graphs and downstream fallbacks. Preserve the first failed redundant-label attempt separately from the revised role-derived-label attempt; this revision is informed development, not an untouched test. Agent-only reference review fulfills the user's chosen exploratory workflow but cannot be described as independent educational ground truth.

## Edge-evidence correction verified

The scoped prerequisite query now applies the same strict source/span predicate to every relationship as every node. Missing, cross-source, future, float, boolean, empty and reversed edge spans fail closed. Legacy unscoped traversal remains unchanged.

Twenty scoped-retrieval tests passed. A real Neo4j control in `artifacts/prerequisite_edge_scope_v2/20260920T142842144842Z/result.json` stored eleven synthetic prior nodes and ten edges in a new namespace. Scoped traversal returned only the valid earlier edge and exact-cutoff edge; it excluded the future edge even though both nodes were earlier, and excluded a hidden earlier prerequisite behind that future edge. Unscoped traversal still returned all ten paths. This is a leakage-control test, not textbook accuracy or educational evidence. Reproduce with `scripts/check_prerequisite_edge_scope.py`.

Case-normalized entity identity and excerpt-coordinate fixes are owned by the root agent and are not certified by this follow-up.
