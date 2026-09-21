# Source-grounded filtering experiment

Declared 20 September 2026 before implementing and scoring the filter. This exploratory design uses the previously reviewed development failures; it is not an independent or preregistered test.

## Question

Can a checker that follows the supplied definitions withhold unsupported model answers while retaining useful coverage? This is a filtering experiment: it cannot increase full-set verdict accuracy by merely rejecting predictions, and it does not claim to improve either model's reasoning.

## Fixed inputs and intervention

Use all 96 model/case records from the completed decomposed development run `20260919T223749942686Z` and all 14 fixture records from `20260919T225703610993Z`. No new inference calls, prompt revisions, correction retries, or model training. Preserve all original predictions and results. Verify input completion hashes, raw-response decoding, case matching, and source/model provenance before replay.

The checker receives only the original public payload and model evidence. It parses a deliberately narrow grammar: explicit one-variable integer function definitions, integer equalities, addition, subtraction, multiplication, and explicitly nonassertive previews. Earlier passages and declared background are admissible. The target position is strict. The checker derives dependencies and expansion from visible text, never from benchmark oracle fields, gold labels, categories, case identifiers, or required-ID lists.

Acceptance requires consistent target interpretation, a correct missing-definition set, all supporting definition citations, and source-consistent substitution structure. Compare arithmetic expression structure after explicitly declared associative normalization; do not accept a wrong derivation just because it happens to give the same number. The restricted syntax and structural matching can reject mathematically valid rearrangements or intermediate simplifications; report that limitation.

The fixed equivalence rule flattens associative addition and multiplication while preserving operand order and every literal; there is no constant folding or commutative reordering. Required source citation IDs must be a subset of the model's admissible citations; extra admissible citations are allowed. Missing-function names must match exactly. Recognized addition-only background does not authorize subtraction or multiplication. Source, background, and preview prose must match the declared narrow parser forms; an unparseable unrelated admissible passage can conservatively make the whole source analysis unsupported.

Unsupported syntax, ambiguity, conflicting definitions, cycles, or bounded-parser limits must not become missing-prerequisite findings. Absence under incomplete context cannot establish a curricular gap. Any new rejection becomes ABSTAIN with a recorded reason; original schema, expression, or runtime errors remain errors. Never replace a model prediction with the checker's answer. The check validates structured evidence within its grammar, not arbitrary explanatory prose or general mathematical truth.

## Comparisons and outputs

- Compare original and filtered verdicts on all 48 development cases for each model; score all seven fixtures separately. Errors and abstentions stay in full-set denominators.
- Report accepted-answer coverage and conditional accuracy with explicit denominators, wrong answers withheld, correct labels withheld, per-category/class results, and rejection reasons. Zero accepted answers has undefined conditional accuracy, never 100%.
- Preserve case pairing. Describe uncertainty over eight development families and disclose that 48 cases contain only 40 distinct complete-context payloads.
- Report the source parser/evaluator alone as a separate deterministic baseline on 48 development cases and seven fixtures. Success on this grammar is a narrow symbolic baseline, not an achievement by the language models or evidence of textbook understanding.
- Store guarded records, reports, source snapshots/hashes, input hashes, and protocol provenance in a new output directory. Keep historical runs intact.

## Decision boundary

Report the accuracy/coverage tradeoff even if the filter catches every observed error. Low coverage would mean the model-checker combination is not yet useful. A strong deterministic baseline would also show that this synthetic task cannot establish a need for an LLM or novelty of the hybrid pipeline. Do not continue prompt tuning merely to improve these familiar synthetic scores.

This replay cannot authorize held-out inference; all 72 held-out cases remain unevaluated. No textbook validity or publication-readiness claim follows. The next research decision must use the observed tradeoff and baseline, rather than a convenient accepted-only score.
