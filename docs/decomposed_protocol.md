# Evidence and calculation development experiment

Declared before new inference on 20 September 2026. This is a development experiment informed by the earlier failures, not a preregistered confirmatory study.

## Question and intervention

Does asking the model for prerequisite evidence and a substituted integer expression, then calculating and selecting the verdict in code, improve full-context classification on the existing development cases?

The intervention combines a changed evidence prompt, a structured evidence contract, arithmetic checking, and deterministic verdict selection. This comparison cannot isolate the contribution of any one component. The model still chooses dependencies and substitutions; checking an expression's arithmetic does not establish that it faithfully represents the source definitions.

## Fixed comparison

- Use every one of the 48 frozen development cases with both existing local models, `qwen2.5-coder:7b` and `mistral:latest`: 96 new inference calls, one per model/case, with no corrective retries.
- Use complete earlier context and supplied background through the existing payload builder. Keep gold labels, categories, oracle structures, and required passage lists out of inference and decision inputs.
- Keep temperature 0, seed 42, a 500-token output limit, and local Ollama. Preserve prompts, raw responses, failures, timings, model identities, source snapshots, and completion hashes.
- Compare with both historical prompts on exactly matching cases and with always-PASS (24/48). Keep schema errors, invalid evidence, runtime failures, truncations, and abstentions in the denominator. Do not reinterpret old invalid responses as valid results.
- Report per-category and per-class outcomes, abstention coverage, gains/losses, and paired differences resampled over the eight dependency families. There are 40 unique complete-context inputs because each missing/future pair is identical after filtering; 48 is not a count of independent tasks.
- Also run the same unchanged intervention on the seven existing engineering fixtures for both models (14 calls). Report every fixture. A passing fixture check is not a substitute for development or educational evaluation.

## Decision and boundaries

Complete the full development comparison regardless of the fixture outcome. Report improvement or regression against each comparator without selecting a favorable subset. Do not change the prompt or rules midway through the run. If implementation defects invalidate a run, preserve it, explain the defect, and declare a separate revision before further inference.

No held-out inference belongs to this experiment. The separate runner cannot authorize that phase, even if it passes all fixtures; any later held-out study requires an explicitly frozen supported protocol and its matching gate. Do not modify the frozen dataset or earlier results. No training, cloud calls, manuscript-result replacement, or submission is included.

The historical baselines are noncontemporaneous and lack recorded weight digests. Matching model names and timestamps do not prove identical historical weights. Timings are descriptive local observations. Results establish neither generalization to new curricula nor naturally occurring textbook defects.
