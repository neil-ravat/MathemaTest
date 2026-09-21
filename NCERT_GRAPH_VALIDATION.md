# Automatic graph validation — 20 September 2026

**Structural validation is stronger, but the next real extraction failed. No model graph was accepted or numerical audit executed in that attempt.** The previous AI-curated reference and original automatic runs remain unchanged.

## Changes tested

Source entities now declare a semantic role, distinguishing quantities, units, instruments, media, controls, circuits, formulas and definitions. A shared validator checks endpoint existence, nonempty unique names, self-edges, duplicate triples, Formula/Theorem role consistency and allowed directional role pairs. Source evidence IDs are range checked; excerpts ending in a question are rejected as assertion evidence. Candidate prerequisites remain separate from accepted `PREREQUISITE_OF` traversal. Roles and claims remain `MODEL_UNREVIEWED`.

75 focused tests passed, including valid and reversed versions of six factual relationship types and rejection of a rhetorical-question citation. One existing Pydantic deprecation warning remains.

[Regression replay](artifacts/ncert_graph_validation_v2/regression_replay.json) rejected seven of the nine earlier edges when supplied with AI-reviewed endpoint roles. Those roles were supplied for the replay, not generated automatically. This measures a regression check, not extraction accuracy.

## Fresh automatic attempt

[Attempt 20260920T140807869900Z](artifacts/ncert_connected_smoke/20260920T140807869900Z/FAILED.json) made one local graph-extraction call. It generated eleven candidate entities and nine candidate relationships, but failed validation for an invalid `CONTROLS` direction/role pairing. The runner stopped before persisting model entities or relationships and before the question audit. It did persist the 226 native input passages in the attempt's isolated source namespace.

[Complete review of the raw result](artifacts/ncert_connected_smoke/20260920T140807869900Z/validation_review.json) identifies:

- Five edges failing direction/role or citation checks.
- Two entity citations using nonexistent evidence IDs 707 and 1120. These match source offsets rather than the supplied excerpt IDs; the cause is inferred from the values, not proven.
- Missing separate charge and time nodes, and no prerequisite candidates.
- Three raw relations judged source-supported in this AI review: current has unit ampere, ammeter measures current, and the current formula expresses current. They were **not** silently salvaged into the database.
- A structurally valid but false relation: **Electric Current HAS_UNIT Coulomb (C)**. The source assigns coulomb to charge and ampere to current. A quantity-to-unit role check cannot establish which unit belongs to which quantity.

## Interpretation and next work

The system now fails closed on more observed errors. It has not demonstrated reliable automatic extraction, a graph benefit, or benchmark accuracy. Model-assigned roles can be wrong; citation existence is not entailment; `DERIVED_FROM` role compatibility is not proof of derivation. The question-ending heuristic is conservative and can reject a mixed statement/question excerpt while missing other rhetorical formulations.

The next development step is evidence-grounded relation selection: separate entity extraction from edge selection, constrain evidence IDs to supplied IDs, and require an independent support judgment for each candidate relation. Any rejected claims and validation failures must remain recorded. Evaluate that change on development material before freezing an evaluation protocol; do not use the manually curated reference as proof of automatic model quality.
