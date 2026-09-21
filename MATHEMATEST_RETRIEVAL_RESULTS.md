# Retrieval improvement: live development check

The defining-law passage and its conditions now reach the heater question. The same model and answer prompt produce three correct numeric values, but the heater explanation contains an incorrect resistance assumption. Only two of three responses are fully acceptable in this AI review.

| Development question | Before | After | Review |
|---|---|---|---|
| Charge | 300 C | 300 C | Correct, source-supported |
| Work | 24 J | 24 J | Correct, source-supported |
| Heater | Abstention | 8 A | Correct value, inconsistent 100Ω assumption |

## Change

Scoped retrieval now searches separately for candidate rule/definition passages using Chroma's text filter plus the same embedding model. A conservative text cue filters candidates, the unchanged reranker selects one, and one of the existing four passage slots is reserved for it. Source identity, prior-position checks and exact original text remain intact. No textbook-specific answer or Ohm-law name was added to the retrieval query. Candidate pool size and selection policy changed; four passages do not imply an equal token budget.

The heater context now starts with original source span [12067,14588), which states V=IR and the constant-temperature condition. All 12 retrieved passages match source bytes and precede their question. Model request parameters, system prompt, question and declared background exactly match the previous live run; only supplied context changed.

## Remaining failure

The heater answer computes (120×4)/60=8A correctly and cites the relevant law. Its assumptions nevertheless say the resistance is 100Ω. The given 60V and 4A imply 15Ω; 100Ω would instead yield 1.2A at 120V. A prior worked example in the retrieved context contains 100Ω, making value carryover a plausible explanation, not a proven causal diagnosis. Core Lean and rational arithmetic cannot detect a contradiction between free-text assumptions and the numeric expression. The response is therefore not scored fully correct.

## Verification and limits

28 focused tests passed, including the reserved slot, deduplication, unchanged four-passage cap and exclusion of future/cross-source rule candidates. Three live model calls used 4626 input tokens and 555 output tokens; the answer pipelines took 70.7s including retrieval and arithmetic/Lean checks. All three arithmetic/Lean checks passed. Energy/cost and total setup time were not measured.

This is tuning on three already exposed Electricity questions, not a fresh accuracy benchmark, graph-benefit result or general formula/diagram evaluation. The heuristic may miss legitimate phrasing or reserve a slot for an irrelevant rule; broader development coverage remains needed. Models and historical outputs are unchanged.

Local evidence: `artifacts/ncert_live_pipeline/20260920T193549227041Z/review.json` and `results.json` · [Earlier live report](MATHEMATEST_LIVE_DEVELOPMENT_RESULTS.md)
