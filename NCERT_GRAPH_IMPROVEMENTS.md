# Source-localized NCERT graph improvements

20 September 2026. The extractor now retains exact, short source excerpts on nodes and relationships, supports specific factual edge labels, and keeps proposed learning dependencies separate from accepted prerequisites. A separate AI-reviewed reference graph is visible in Neo4j. Automatic semantic extraction is still unreliable.

## Implementation and checks

- Source text is divided into numbered sentence-like excerpts without rewriting its characters. The model selects evidence IDs; code validates them and derives exact original offsets. These excerpts are heuristic boundaries, not certified semantic units.
- Added `MEASURES`, `FLOWS_THROUGH`, `CONTROLS`, `EXPRESSES`, `USES_QUANTITY`, `HAS_UNIT`, and `CANDIDATE_PREREQUISITE_OF`. Source-mode extraction cannot emit accepted `PREREQUISITE_OF` edges. Candidate edges are excluded from the existing accepted-prerequisite traversal.
- Node and edge citations have explicit review status. Exact text matching confirms provenance, not entailment. Model output remains unreviewed until separately assessed.
- Duplicate edge triples are rejected to prevent citation overwrite through Neo4j MERGE. This guard was added while inference was running; the saved raw output was subsequently revalidated with the updated schema and contains no duplicate triples. The run snapshot predates this final guard.
- 68 focused tests passed. Actual Neo4j checks confirmed all reference citations match the original text, ten nodes and twelve edges persisted, and candidate prerequisites produce zero accepted-prerequisite results.

## Actual automatic run

[Run 20260920T135952433150Z](artifacts/ncert_connected_smoke/20260920T135952433150Z/COMPLETE.json): two local inference calls, ten entities, nine relationships, twelve retrieval boundary checks with zero violations, and Example 11.1 answered **300 C / ARITHMETIC_CHECKED**. The arithmetic proof does not certify the graph, units or question mapping. No prerequisite candidate was generated automatically.

The graph's citations are now localized, making semantic problems visible: two of nine edges were supported as written in this AI review (Switch CONTROLS Electric Circuit; Ammeter MEASURES Electric Current). Other edges reversed direction, confused units with quantities or cited rhetorical questions as evidence. Charge and time remained missing as separate nodes. This is a development observation, not an independently adjudicated accuracy score. Original model output and database records were preserved.

## Separate reviewed reference

Namespace: `ncert-jesc111-reviewed-reference-v1`.

[Reference data and automatic-run review](artifacts/ncert_graph_review_v1/graph.json) and [actual database verification](artifacts/ncert_graph_review_v1/database_verification.json).

This graph was manually curated by the AI from the same source after inspecting the automatic result. It is a development reference, **not automatic extraction, teacher gold, or benchmark evidence**.

- Ten nodes explicitly include electric charge, elapsed time, current, the current formula, ampere and coulomb.
- Nine factual relationships capture flow through a conductor, formula meaning and quantities, units, current measurement and switch control.
- Three candidate learning dependencies link interpreting charge, time and current to understanding the current formula. Their source supports the quantities and symbols; the learning dependency itself is a pedagogical suggestion. They are not accepted prerequisites.
- Every node and edge includes its original source excerpt and offsets. No original run was overwritten, and no comparison benchmark was run with these manual corrections.

```cypher
MATCH (a {source_id:'ncert-jesc111-reviewed-reference-v1'})-[r]->
      (b {source_id:'ncert-jesc111-reviewed-reference-v1'})
RETURN a,r,b;
```

Next: independently adjudicate this reference, improve automatic direction/entailment checks on development material, and freeze a version before evaluation on fresh examples. Do not promote candidate prerequisites or claim graph benefit from the 300 C answer alone.
