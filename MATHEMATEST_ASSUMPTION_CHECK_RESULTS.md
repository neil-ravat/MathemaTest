# Assumption consistency: live development check

MathemaTest now rejects the observed resistance contradiction before publishing an answer or invoking Lean.

| Question | Live outcome |
|---|---|
| Charge | 300 C accepted; arithmetic/core Lean passed |
| Work | 24 Joules accepted; arithmetic/core Lean passed |
| Heater | REJECTED_ASSUMPTION: stated 100 Ω conflicts with 60 V / 4 A = 15 Ω |

The raw heater response still calculates 8 A correctly. Its inconsistent assumption is retained in the raw judgment and diagnostic report, but there is no accepted answer or Lean certificate for that response. This improves failure detection, not generated-solution correctness.

The model, prompt, generation parameters, questions and context text/offsets match the previous run. Two request bodies are identical. The charge request differs only in one citation ID belonging to an alternative graph entity with the same source excerpt.

The deterministic guard handles one explicit voltage/current operating point, requires a cited R=V/I or V=IR formula, normalizes supported unit prefixes and compares explicit numeric resistance claims with exact fractions. Ambiguous wording, unsupported formulas, multiple operating points, explicit state changes and zero-current inputs remain unassessed. It does not verify every assumption, establish general physical applicability, or correct the response. Existing source/units verification flags remain false.

74 focused tests passed. Replaying the saved responses through the final guard reproduces all live dispositions. Additional conservative state-change exclusions were added during inference; both the run snapshot and final implementation copy are retained. This is tuning on three previously exposed development cases, not expert gold or a fresh benchmark.

Three model calls used 4625 input and 555 output tokens. Answer pipelines took 68.2s; setup and review overhead are excluded.

Local evidence: `artifacts/ncert_live_pipeline/20260920T194205948226Z/review.json` and `results.json` · [Guard implementation](src/verification/assumption_consistency.py)
