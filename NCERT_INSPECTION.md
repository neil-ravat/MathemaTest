# NCERT pilot inspection - 20 September 2026

This is a development review of twelve selected worked examples from Class 10 Mathematics (Quadratic Equations) and Science (Electricity). It is not a complete textbook audit or a teacher-labeled benchmark.

**Status: all three inspections completed.** All twelve selected calculations check out under the documented assumptions. No missing-prerequisite defect was established. Formula extraction needs repair, and Electricity Example 11.4 needs an explicit interpretation of its constant-resistance assumption. No full raw context prefix is certified ready for model input.

James verified eight source PDF/text hashes, two dataset-output hashes and the builder hash; all 35 page slices and twelve target/context boundaries match. The two existing preparation tests passed. A final snapshot comparison confirmed that all fifteen source-package files remained unchanged during inspection. Six reviewer report files were parsed or hashed in `inspection_checks.json`.

## Review assignments

- **[Meowth](artifacts/ncert10_pilot_v1/inspection/meowth.md):** six Mathematics examples; mathematical checks, prerequisite evidence and formula extraction.
- **[Jessie](artifacts/ncert10_pilot_v1/inspection/jessie.md):** six Electricity examples; calculations, units, physical assumptions and source references.
- **[James](artifacts/ncert10_pilot_v1/inspection/james.md):** source hashes, candidate boundaries, answer leakage and evaluation design.

Reports are saved separately in [the inspection folder](artifacts/ncert10_pilot_v1/inspection/README.md). The agents worked on separate scopes, with access to existing preparation notes. These are AI reviews, not blinded human judgments or an inter-rater reliability study.

## Evaluation decisions

The pre-solution input and a textbook editorial audit answer different questions. For a pre-solution diagnostic, the target's worked solution must stay out of the input. However, a worked example can itself introduce a method: inability to solve it beforehand does not prove the textbook omitted required instruction. Mathematics Example 3 explicitly introduces how prior factorisation knowledge is used to find roots (PDF page 5, printed page 42).

Electricity Example 11.3(a) cites Eq. (12.6) in its solution, while part (b) cites the relevant Eq. (11.6) (PDF page 9, printed page 179). The bad reference is outside that example's proposed input. A model cannot be scored as failing to detect it from a prompt that excludes it. Detecting this reference belongs in a separate editorial task with the relevant solution visible.

Full-page images are review material. They may show both the question and its solution; passing them into a pre-solution model run would leak answers. Future inputs need checked transcriptions or precisely bounded image regions. Dataset reviewer notes, answer calculations and these reports must also stay out of model inputs.

Earlier-chapter prefixes omit previous chapters and grades. Explicitly assumed background must be recorded separately. Damaged extraction and unavailable background evidence require an uncertainty outcome, not a claim that a textbook prerequisite is missing.

## Next diagnostic gate

Before running the models, freeze the task definition, permitted background and reviewed input content. Verify the equations, tables and units actually supplied to each model. Keep any corrections traceable to the source; preserve raw extraction separately. Review of selected evidence does not certify every page in the raw prefix.

Without independent educational labels, report response validity, evidence support, numerical consistency and abstention counts with their denominators. Do not report prerequisite-detection accuracy, teacher agreement or textbook defect prevalence.

No NCERT benchmark inference or synthetic held-out evaluation was performed for this inspection. Source-file preservation is recorded separately in the inspection folder.
