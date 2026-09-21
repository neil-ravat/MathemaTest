# MathemaTest pipeline fixes

This revision changes ingestion and corpus construction, not model weights, model selection or solver prompts.

## Changes

- The image/PDF ingestion path now runs installed Tesseract on detected English prose, title, list and caption crops instead of returning placeholders. Page/block provenance and bounding boxes remain attached to successful content. Tesseract has a 60-second per-block timeout; missing executables, empty OCR and subprocess failures are reported as ingestion errors.
- Empty formula OCR and unsupported figures/tables/unknown regions are reported rather than emitted as extracted evidence. Successfully extracted prose survives failures in other blocks. Unsupported visual regions are identified by page and bounding box for review. General mathematical OCR and diagram interpretation remain unfinished.
- Shared chapter graph construction now ends at the earliest selected target start. It previously ended at the last target start, exposing earlier selected questions and their solutions to graph construction. This stricter prefix can reduce graph coverage, but excludes all selected targets from construction. Query-time source filtering still applies.

## Verification

47 focused tests passed, including actual local Tesseract extraction of a printed sentence into structured output, partial-page failure handling, earliest-target cutoff, existing integration/native-text extraction and baseline scope checks. One existing Pydantic deprecation warning remains.

Command: `.venv/bin/python -m pytest -q tests/test_ingestion_content.py tests/test_integration.py tests/test_digital_ingestion.py tests/test_ncert_baselines.py`

The OCR smoke uses a synthetic prose image and a supplied layout test double. It does not establish automatic layout detection, NCERT formula fidelity or end-to-end answer accuracy. The native pdftotext route is unchanged; these fixes do not repair its known flattened fractions or missing diagrams. No frozen study predictions or historical code snapshots were rewritten; future corpus builds use the new cutoff. No inference or graph rebuild was needed for these regression checks.

## Equation and diagram region ingestion

`IngestionEngine.process_pdf_region(pdf_path, page_number, bbox, output_dir)` now exports a selected crop at 144 dpi together with exact native text spans, font sizes, PDF-point boxes, PDF/image hashes and candidate readable text. Coordinates use the displayed page's top-left origin. Output directories must be new. The ordinary native-text extraction route and its historical offsets remain unchanged.

Adjacent raised small integer runs become candidate superscripts. Simple vertically stacked alphanumeric tokens become fraction candidates only when image pixels show a continuous printed bar between them. Raw spans remain unchanged for inspection. Diagrams retain vector-rendered pixels, including arrows and component symbols; their semantics are not automatically understood. All packets remain `INPUT_REVIEW_REQUIRED` / `solver_ready=False`. Providing a region via `AuditorProver.audit_question(..., question_region=packet)` returns that status before retrieval or inference. Existing plain-text calls still require the caller to ensure faithful transcription; this is not automatic detection of every damaged input.

Development crops in `artifacts/pdf_region_development_v3/` were visually inspected: the quadratic expression preserves its exponent, the current formula becomes `I = (Q)/(t)`, and the complete electric circuit retains its arrows, cell, lamp, ammeter and switch. All three final crops have zero clipped native spans. Earlier crop attempts are retained in v1/v2; v1 contains incomplete selections, not usable final examples.

35 focused tests passed, including real pinned-PDF crop extraction, visible-bar versus no-bar fraction detection, superscript constraints, invalid bounds, non-overwrite behavior and stopping unreviewed inputs before a model call. These are engineering/development checks, not fresh accuracy results. General nested fractions, radicals, handwritten mathematics, automatic question/solution boundary selection and diagram interpretation remain unresolved. Region boxes in the development examples were selected by the agent after page inspection. No model was switched or trained, and no frozen evaluation was rerun.

## Factual relationship acceptance

Added the shared `explicit_clause_v1` source-text witness policy for all seven factual relationship types. Staged extraction now requires an explicit directional clause in the cited excerpt in addition to model approval and endpoint-role compatibility. Neo4j persistence rechecks the same condition, including calls through the older extractor, and counts quarantined relationships. Rejected proposals remain in extraction reports or their in-memory result with a reason; they are not silently classified as false.

The policy matches narrow affirmative clause templates, including explicit unit and measurement statements. Co-occurrence, reversed endpoints, negated/conditional/questioned claims and unknown wording do not qualify. This is a conservative lexical filter, not a general entailment proof; valid paraphrases, multi-sentence derivations, aliases and qualified statements may be quarantined. It does not correct all entity roles or descriptions. Legacy non-factual relationship types remain outside this policy.

78 focused tests passed, including positive directional examples, adversarial wording, staged extraction with an incorrectly approving reviewer, persistence-boundary enforcement and existing source/retrieval checks. A post-evaluation replay quarantined all nine previously audited edges (eight unsupported, one partly supported). See `artifacts/graph_relation_guard_development_v1.json`. This is development regression evidence, not a new accuracy benchmark or a measured recall result. Original predictions, stored historical graphs and audit artifacts were not modified. Future extraction/persistence uses the revised policy; no live graph rebuild or model call was performed.

## Coverage regression and repair

Testing `explicit_clause_v1` against the previously AI-reviewed Electricity development candidates exposed excessive rejection: it retained 0 of 4 supported candidates (the historical pre-v1 pipeline retained 2). `explicit_clause_v2` supports the attested named-instrument measurement sentence, unit naming with a naming attribution, and explicit lists of current units. It retains 4 of 4 in this small candidate set while rejecting the incorrect current-to-coulomb candidate. Numeric unit conversions inside parentheses are not certified by accepting unit membership.

Saved-output replay through staged extraction and the persistence boundary retained 11 nodes and 4 relationships. Persistence used an in-memory test double: no live database write or new inference was performed. All 9 previously flagged evaluation edges remain blocked. 79 focused tests passed. Artifacts, before/after source snapshots and candidate-level evidence are in `artifacts/graph_coverage_development_v2/`.

This is explicitly development tuning on previously inspected candidates, not independent evaluation, general extraction recall, or evidence of improved end-to-end answering. Missing charge/time/formula entities and diagram interpretation remain unresolved. Frozen runs and underlying models remain unchanged.
