# NCERT graph review through Neo4j Browser

Reviewed live at http://127.0.0.1:7474/browser/ on 20 September 2026, using read-only Cypher queries entered through the browser UI. Scope: source `20260920T134850055778Z-jesc111`, the successful connected smoke. No graph records changed. This is an AI engineering/content review, not teacher adjudication.

## Findings

The graph contains eight extracted entities and four edges: three `GROUNDED_IN`, one `DERIVED_FROM`, and no `PREREQUISITE_OF`. Electron and SI Unit of Charge are isolated. The graph has four disconnected components. Global database totals include other attempts and synthetic controls and must not be presented as this run's totals.

| Actual directed edge | Assessment against stored source | Proposed representation, not applied |
|---|---|---|
| Electric Current —GROUNDED_IN→ Conductor | Source supports charge flowing through a conductor. This is a flow/medium association, not evidence of a learning prerequisite or an instance-of relation. | Electric Current —FLOWS_THROUGH→ Conductor, if factual relation types are added. |
| Current Formula —DERIVED_FROM→ Electric Current | Source defines current as charge per unit time and presents I = Q/t. The formula expresses that definition; the record does not supply a mathematical derivation. | Link the formula to an explicit current definition with a definition/formalization relation. |
| Electric Circuit —GROUNDED_IN→ Switch | Source describes a switch making/breaking the conducting link. The edge hides the control relation; a switch is not established as a prerequisite for understanding a circuit. | Switch —CONTROLS→ Electric Circuit. |
| Ammeter —GROUNDED_IN→ Electric Current | Source explicitly says the instrument measures current. `GROUNDED_IN` hides this meaning. | Ammeter —MEASURES→ Electric Current. |

These proposed labels are design suggestions, not supported production schema additions. Keeping the existing narrow schema would instead require omitting factual associations that do not fit its semantics. Do not relabel all associations as prerequisites just to increase traversal counts.

## Missing structure

- Electric charge and elapsed time appear in the formula description but have no separate nodes. Ampere and its relation to coulomb per second are present in the source but absent as explicit graph concepts/relations.
- Electric Current's description says flow of charge but omits the source's stronger quantitative definition: charge per unit time. That distinction matters for solving Example 11.1.
- Electron and SI Unit of Charge have no edges despite source-supported relationships with current/charge. Not every source concept is necessary for this particular question; their isolation is a coverage issue, not proof that adding those edges would improve the answer.
- All eight entities point to the same source span `[0, 4303)`. Provenance is retained, but individual definitions and relationship evidence are not localized. Entity-specific source sentences are needed for a meaningful evidence audit.
- Minute-to-second conversion was explicitly supplied as background in the smoke. A future graph must distinguish declared background from information extracted from the textbook.

## Recommended next change

Separate factual associations from proposed learning dependencies. First localize the current definition, charge/time quantities and units in the source. Then review candidate dependencies needed to interpret and rearrange I = Q/t, distinguishing textbook evidence from pedagogical judgment and declared arithmetic background. Freeze the reviewed version separately from this original model output before a graph-versus-vector comparison.

Browser graph query used (includes isolated extracted nodes):

```cypher
MATCH (n)
WHERE n.source_id = '20260920T134850055778Z-jesc111'
  AND n.entity_review = 'MODEL_UNREVIEWED'
OPTIONAL MATCH (n)-[r]-(m)
WHERE m.source_id = n.source_id
RETURN n, r, m;
```

The undirected display query returns each edge from both endpoint rows; its ten records correspond to eight unique nodes and four unique edges, not eight edges.
