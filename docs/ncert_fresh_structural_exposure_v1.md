# Fresh graph construction exposure disclosure v1

Recorded during the frozen corpus construction, before comparative answer predictions were inspected. This disclosure does not change the run, candidate set, scoring rubric or model prompts.

The builder's declared graph-prefix rule is source start through the **last selected target start** in each chapter. Code computes the maximum selected target offset. For an earlier selected target in the same chapter, graph construction can therefore see that target and its worked solution. The model's selection of entities, descriptions, cited earlier passages and relationship topology can be influenced by this later information even when retrieval subsequently filters every supplied excerpt to precede the individual target.

Source-ID, exact-text and node/edge offset guards prevent direct retrieval of future excerpts. They do **not** remove this structural exposure. Report the frozen study as a factual augmentation diagnostic over a graph-informed shared index; do not call it fully target-blind, leakage-free, or a valid clean temporal generalization test. Both retrieval arms share the affected native-plus-entity index, which narrows the comparison to factual-edge augmentation over that index but does not eliminate the exposure.

Keep every selected target and outcome in the denominator. Do not exclude first targets, rewrite the graphs or rerun this frozen study to hide the issue. Attach an exposure flag per case based on whether its start is less than the graph-construction cutoff; this metadata can be calculated without reading answer content. AI reference reviewers must still remain blind to model predictions.

A future corrected study must build each target's graph only from its own admissible earlier prefix, or use a rigorously immutable incremental graph whose earlier entity selection and topology cannot be influenced by later text. It requires new uninspected targets and a separately frozen version. The present disclosure is not evidence that every prediction used a leaked answer; it establishes that the current design cannot exclude that pathway.
