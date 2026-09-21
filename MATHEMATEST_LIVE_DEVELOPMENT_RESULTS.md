# Live MathemaTest development check

The isolated live run completed with the fixed Qwen producer/auditor and Mistral reviewer. Two of three previously exposed Electricity questions produced correct, source-supported numerical answers; one abstained. This is an engineering development check, not a fresh benchmark.

| Question | Expected | Actual | Verification |
|---|---|---|---|
| Charge, 0.5 A for 10 minutes | 300 C | 300 C | Exact arithmetic and core Lean passed; AI source review adequate |
| Work, 2 C across 12 V | 24 J | 24 Joules | Exact arithmetic and core Lean passed; AI source review adequate |
| Heater, 60 V/4 A changed to 120 V | 8 A if resistance stays constant | Abstained | Missing general-law context; no answer verified |

The live graph retained 11 entities and four source-supported factual edges: current to ampere/milliampere/microampere and ammeter to current. The wrong current-to-coulomb proposal was rejected by the source-text check despite model-review approval. Every stored edge has exact source provenance and ends before the first selected target (offset 4303). The 11 node descriptions/excerpts exactly repeat the earlier audited development extraction, including four descriptions with only partial support. Edge acceptance has improved; full node quality remains unresolved.

All 12 retrieved passages match their source bytes and precede their respective questions. No prerequisite paths were expanded. The production scoped retrieval path traverses prerequisite relationships, not these factual relationships; extracted nodes can still appear as vector seeds. This run therefore does not establish a factual-graph benefit.

For the abstention, retrieval selected the previous bulb/heater example (which uses I=V/R), a charge question, an Ohm-law activity and a table. It omitted the explicit law and fixed-temperature condition. The model focused on declared background and incorrectly claimed that no relevant formula was available, despite the worked-example evidence. The next engineering target is retrieving the defining law and its conditions, then checking that the auditor uses those passages.

## Cost and limits

Six local model calls: three construction/review calls and three auditor calls. Construction request time was 200.8s; the three answer pipelines took 60.7s including retrieval and verification. Total reported tokens: 9541 input and 2790 output. These timings exclude other setup/inspection, and hardware/electricity cost was not measured.

The three question statements were visually checked against their PDFs; printed solutions were co-visible and these cases were already exposed. Native source formulas were not silently rewritten. This does not test general diagram interpretation, fresh generalization or the entire legacy calculus/Mathlib workflow. 31 focused engineering tests passed before answering. Models were not switched or trained; historical graphs and predictions were preserved.

## Artifacts

- Live results: `artifacts/ncert_live_pipeline/20260920T192727832616Z/results.json`
- Source and answer review: `artifacts/ncert_live_pipeline/20260920T192727832616Z/review.json`
- Live graph snapshot: `artifacts/ncert_live_pipeline/20260920T192727832616Z/graph_snapshot.json`
- Construction artifacts: `artifacts/ncert_study_corpus/20260920T192315449639Z`
