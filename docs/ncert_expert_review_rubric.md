# Independent NCERT review rubric v1

Status: an AI review instrument under the user’s agent-only preference, not independent expert ground truth. The 12 packet cases are exposed development material. No model predictions, AI transcriptions, AI reviewer notes or proposed answers appear in the packet. Subject/source identity remains visible because it is necessary to locate evidence; “blind” means prediction-blind, not source-blind.

Use two separately assigned agents A and B, withholding system predictions and each other's annotations until both are saved and hashed. Disclose prior conversation exposure and source/solution consultation. A third pass records adjudication against original evidence. Label outputs `AI_REFERENCE_NOT_EXPERT_GOLD`; shared models and prior context limit independence. User preference makes human review optional future validation, not a prerequisite to running this exploratory comparison. The blank reviewer forms retain a qualification field; enter the agent role/model if known and explicitly “not a human subject expert.”

## Independent pass

1. Open `artifacts/ncert_expert_review_v1/review.html` locally. Copy your blank JSON to a separate working file. Do not overwrite the blank packet. Correct raw target transcription against the PDF; mark damaged or ambiguous notation. First solve independently; then consult the official solution if useful and record that consultation and prior familiarity. A printed answer is a reference to check, not infallible expert adjudication.
2. Record every subpart's answer, units, exact derivation and acceptable equivalent forms. Exact rational/algebraic answers are preferred; specify a justified tolerance only where the source expects rounding. Do not give a global numerical tolerance that could mask unit errors. A multipart example is one evaluation family; report subpart accuracy separately.
3. List minimal knowledge needed to solve this target, distinguishing facts from learning dependencies. For each prerequisite use `{concept, required_for, rationale, status}`; status is `SUPPORTED_EARLIER`, `DECLARED_BACKGROUND`, `UNRESOLVED`, or `NOT_NECESSARY`. Direction is prerequisite → dependent skill. Do not declare every related entity necessary.
4. For each supporting passage use `{source_id, pdf_page, printed_page, exact_quote, start_offset, end_offset, supports}`. Offsets are optional when native text is damaged; mark unavailable rather than inventing coordinates. Offsets count Unicode characters in the hashed extracted text. Earlier support must end at or before the target start; the target's own question and solution are not earlier evidence. Cross-chapter/grade support needs an identifiable original source and locator.
5. Record required prior-course background explicitly with source/grade/rationale. Current packets contain only earlier text in one chapter, not the complete curriculum. Choose `UNCERTAIN_CONTEXT` if incomplete earlier-grade material prevents a curriculum judgment. Do not convert retrieval failure into an educational defect.
6. Set `curricular_judgment` to `ADEQUATE`, `REASONABLE_BACKGROUND`, `INTENTIONAL_PREVIEW`, `MISSING_PREREQUISITE`, `MATHEMATICAL_ERROR`, `EDITORIAL_ISSUE`, or `UNCERTAIN_CONTEXT`. A missing prerequisite requires a necessary dependency, a declared learner profile, a sufficiently complete curriculum search and rationale excluding legitimate assumed background. Record confidence as `HIGH`, `MEDIUM`, or `LOW`, with unresolved issues.

For graph-edge review, source truth and pedagogical necessity are separate fields. An exact quote must support the named endpoints, relation and direction; a mere mention does not entail the edge. Mark proposed prerequisite necessity separately. AI-reviewed or AI-curated edges are never independent human gold.

## Lock and adjudicate

For the first two development cases per subject, reviewers complete a calibration round independently, then discuss rubric ambiguities. These calibration cases remain development only. Any rubric revision gets a new version before remaining reviews. Keep all initial labels; do not overwrite disagreements. Collect both remaining independent JSON files, hash them and record completion times before joint discussion. The adjudicator writes a separate record containing case ID, both original judgments, final judgment, evidence and decision reason. Unresolved cases stay uncertain; they are not silently excluded after predictions.

Report raw agreement and the confusion table for curriculum categories, plus Cohen's kappa only if the observed marginals make it meaningful. Report answer agreement and prerequisite-set agreement separately; neither is a substitute for category agreement. Measure source-citation correctness against original pages, not against an AI-generated graph.

## Optional future independent expert validation

- Two qualified, independent reviewers covering Class 10 mathematics and physics, and an adjudicator.
- Agreement on the intended learner background and the earlier-grade/chapter source corpus.
- Completed separate annotations and adjudication; source/formula QA of any fresh cases.
- A custodian who can lock fresh inputs/labels without showing answer keys to system developers.

No expert has supplied packet labels. Agent reviews do not fulfill independent expert validation; this limits claims but does not stop the requested agent-only study. NCERT PDFs stay local; obtain appropriate permission before redistributing textbook content.
