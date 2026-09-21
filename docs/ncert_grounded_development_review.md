# Grounded NCERT development graph: source audit

**Status: manual AI development audit, not expert gold.** Only run `20260920T143137143546Z` and its original Electricity prefix were inspected. No fresh evaluation content was opened. Prior development exposure is disclosed.

The retained graph contains 11 entities and 2 factual edges. Both edges are supported. Four retained entity descriptions exceed their actual cited excerpts: Electricity, Conductor, Switch and Ampere. Their plausibility does not make the short citations sufficient. Seven remaining entities are supported by the original source; three unit descriptions need visual exponent checks because extracted typography is incomplete.

## Retained entities

| Entity | Strict support | Finding |
|---|---|---|
| Electricity | PARTIAL | The cited sentence establishes importance in society, not that electricity is energy or its applications. Adjacent source prose supplies those additional claims; the actual citation stops too soon. |
| Electric current | SUPPORTED | The excerpt explicitly equates charge flow through a conductor with electric current. Quantitative rate-of-flow definition is elsewhere in dev source and omitted from description. |
| Conductor | PARTIAL | The excerpt uses conductor and gives metallic wire as an example while defining current. It does not explicitly define conductor as a material allowing current; that general property is a plausible inference, not strict definitional entailment. |
| Electric circuit | SUPPORTED | Exact definition of continuous closed current path appears in cited excerpt. |
| Switch | PARTIAL | Cited sentence states that a switch makes the conducting link. Breaking a circuit and stopping flow requires the later sentence about the switch being turned off, absent from this citation. |
| Electric bulb | SUPPORTED | Torch bulb glowing when current flows supports the basic stated function; no advanced operating-condition claim is included. |
| Ammeter | SUPPORTED | The excerpt explicitly states that the ammeter measures electric current. |
| Coulomb (C) | SUPPORTED_WITH_VISUAL_NOTATION_CHECK | Charge unit is explicit. The raw excerpt flattens 10^18 to 1018; PDF page2 visually confirms the exponent. Thus original-source support is sound, but raw text alone does not certify the exponent. The electron charge comparison is magnitude language. |
| Ampere (A) | PARTIAL | Cited excerpt establishes current unit name only; it does not include one coulomb per second. The immediately following source sentence does establish that definition. |
| Milliampere (mA) | SUPPORTED_WITH_VISUAL_NOTATION_CHECK | Cited source states current may be expressed in mA and gives 1mA=10^-3A. PDF page2 verifies exponent placement. |
| Microampere (µA) | SUPPORTED_WITH_VISUAL_NOTATION_CHECK | Cited source states current may be expressed in microamperes and gives 1microA=10^-6A. PDF page2 verifies exponent placement. |

All 13 retained items’ character offsets match the original extracted text exactly. That mechanical check succeeds even for inadequately supported descriptions.

## Edges and rejection tradeoff

The two retained edges are `Electric current HAS_UNIT Ampere` and `Ammeter MEASURES Electric current`. Their citations explicitly support relation and direction. Neither asserts educational necessity.

The model reviewer incorrectly accepted `Electric current HAS_UNIT Coulomb`; source excerpt 25 actually assigns coulomb to charge. The deterministic guard correctly blocked it. The same guard falsely blocked current→milliampere and current→microampere, both explicitly supported in excerpt 29. Candidate-level result: of five proposed unit/measurement edges, four have source support, two survive, one false edge is blocked. This is a small development diagnostic, not general precision/recall.

The cell chemical-reaction description was correctly withheld because its selected excerpt does not mention cells or chemistry. The source nevertheless describes cells supplying charge flow in the torch; a modest supply-role node/edge remains missing.

## Coverage gaps

- **Electric charge Q quantity:** Coulomb node has no charge endpoint; charge-current confusion cannot be repaired into the true HAS_UNIT edge. Source PDF page 2, character offsets [2211,2361).
- **Time t quantity:** No time role for I=Q/t. Source PDF page 2, character offsets [2211,2361).
- **Current-charge-time formula I=Q/t:** No formula entity or formula-variable links; raw fraction layout requires care but original PDF clearly supplies the relation. Source PDF page 2, character offsets [2211,2542).
- **Rate-of-charge-flow definition:** Current description remains qualitative; quantitative dependency on charge/time not represented. Source PDF page 1, character offsets [1445,1606).
- **Circuit and switch relation:** Entities exist but no switch/circuit/flow control edge; makes versus breaks should be grounded across adequate span. Source PDF page 1, character offsets [1120,1404).
- **Cell supply role:** A source-faithful cell role could be retained without chemical-reaction embellishment; neither cell nor supply relation survives. Source PDF page 1, character offsets [866,1023).
- **Ammeter series connection:** Measurement edge retained, but source-stated series-connection role omitted. Source PDF page 2, character offsets [3355,3658).
- **Conventional current direction:** No directed terminal/current-flow representation. Source PDF page 2, character offsets [3937,4190).

The circuit, switch, bulb and conductor nodes are largely isolated; retained edges center on current units and measurement. Charge and time quantities plus the explicit I=Q/t formula are absent. Consequently the graph cannot yet be treated as a complete representation of even this short introductory passage.

## Interpretation

Keep source factuality, citation sufficiency, formula extraction fidelity and pedagogical necessity separate. Four partial entity claims are false acceptances under a full-description entailment rule, not four proven false physics facts. Correct nearby evidence could repair several citations, but that repair was not performed in this audit. No production code or frozen extraction was modified.

Detailed offsets, source quotations and input hashes: [dev_source_audit.json](../artifacts/grounded_graph_pilot/20260920T143137143546Z/dev_source_audit.json).
