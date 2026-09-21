# Fresh exploratory AI scoring rubric v1

Declared before fresh comparative predictions are inspected. The user selected agent-only checking. All labels and scores are **AI-reviewed reference agreement, not independent expert accuracy**. This rubric is fixed for the ten selected fresh families; revisions require a separate version and cannot silently rescore an earlier outcome.

## Blinding and reference pass

Freeze all scheduled model attempts, including errors, before opening source solutions for reference annotation. Record hashes in a prediction lock that also identifies the candidate-input hash. Separate reviewers A and B receive only source questions, original pages, earlier admissible passages and blank fields. They do not receive model outputs or each other's annotations. Record their previous exposure, any extraction correction and solution consultation. Preserve and hash both completed reference files before comparison. Source corrections discovered in this pass do not change already executed model inputs; report them as input-fidelity limitations.

Each reference records all subpart answers, exact or acceptable equivalent forms, units, derivation, necessary physical assumptions, prerequisite candidates and exact earlier-source evidence. Use exact answers when possible. Specify justified rounding/tolerance per case before reading predictions; never enlarge tolerance to accept an observed model answer. Printed solutions are checked against a derivation rather than treated as unquestionable truth. A separate adjudication pass resolves reviewer disagreement from source evidence and records both originals. Unresolved cases remain `UNCERTAIN_REFERENCE`; no outcome-driven replacement or deletion.

Only after references are locked may scoring reviewers see outputs. Hide system-arm labels and present a stable shuffled order when preparing their scoring packet. Reference reviewers' prior familiarity with public textbook material limits independence, as do shared model families. These limitations stay attached to results.

## Answer category — one per attempted arm/family

Apply these categories in order; a multipart example is one family:

1. **ERROR:** infrastructure failure, unavailable required graph under the declared policy, incomplete/truncated response, invalid schema, or other runner failure prevents an admissible answer. A correct-looking number in an invalid response does not become an accepted system answer. Record error subtype and raw-response availability separately.
2. **ABSTAIN:** a valid response explicitly withholds a solution and supplies no substantive attempted answer. A successful refusal is not a correct solved answer; report coverage separately. A response declaring abstention while also providing a substantive answer is a contract inconsistency, recorded as ERROR if the schema/policy forbids it.
3. **COMPLETE:** every requested subpart and requested quantity is correct, with acceptable equivalent forms and required units. Material assumptions are stated where needed for the proposed solution. A demonstrably false derivation or contradiction that undermines the answer prevents COMPLETE even if its final number matches. Equivalent valid derivations are allowed; matching the reference's wording or algorithm is unnecessary unless the question explicitly requests a method.
4. **PARTIAL:** at least one requested subpart or material intermediate result is correct, but one or more required answers, units, conditions, explanations or requested methods are missing or wrong. A correct scalar with wrong units is at most PARTIAL. State exactly which parts are correct; do not assign an arbitrary fractional score.
5. **INCORRECT:** a valid substantive attempt supplies no materially correct requested result, or gives a contradictory/wrong final conclusion. An unsupported claim of logical contradiction is not automatically a correct detection. Explanatory prose alone does not earn partial credit unless it establishes a meaningful requested intermediate result.

If source ambiguity prevents distinguishing these categories, set `reference_resolvable:false` and `answer_category:null` with the ambiguity reason, while retaining the arm's operational status. If the input transcription is damaged, record both `raw_input_fidelity` and answer category relative to the intended original question where assessable; do not credit a different problem as COMPLETE. Report an additional answer-to-raw-input judgment only as a separate diagnostic, never a replacement primary score.

A valid conditional answer can be COMPLETE when it explicitly states the condition needed for the textbook model and otherwise solves every subpart. A condition that evades the requested problem or changes a stated fact is not acceptable. For science, distinguish physical quantities from their units and apply compatible unit conversions before comparing values. For algebra, compare root sets with multiplicity where requested; order is immaterial. For diagrams, inspect the original image; missing diagram access becomes uncertainty or input failure rather than an invented answer.

## Evidence support — separate from answer category

Score retrieval-arm source support as `ADEQUATE`, `PARTIAL`, `UNSUPPORTED`, or `UNCERTAIN`.

- ADEQUATE: admissible cited original passages support the material subject premises used in the answer; declared background covers remaining routine operations. Citations are real, source-order valid and semantically relevant. Legitimate mathematical consequences of supported premises are allowed; the answer itself need not appear verbatim.
- PARTIAL: some necessary subject premises are supported but a material dependency is omitted or cited inadequately.
- UNSUPPORTED: cited text is absent, later, wrong-source, unrelated, contradictory, or no required subject evidence is supplied.
- UNCERTAIN: source extraction or reference ambiguity prevents semantic adjudication.

Record citation validity separately from semantic entailment, with passage IDs and precise reasons. Exact source offsets prove provenance, not truth. Extra irrelevant valid citations are recorded as citation imprecision; they do not erase adequate necessary support unless they introduce a material contradiction. A model cannot certify its own claim by citing its generated graph description. Original graph-associated excerpts remain eligible if verified.

For direct answers, evidence support is `SOURCE_UNAVAILABLE`, not automatically UNSUPPORTED. Direct is scored as an answer-only secondary comparator; it cannot receive the retrieval-arm grounded-success score. Correct arithmetic or successful Lean compilation is an independent engineering field and cannot certify units, source fidelity or educational adequacy.

## Prerequisite judgments — separate, provisional

Map proposed prerequisites to the adjudicated AI reference concepts, allowing documented semantic synonyms. Record supported necessary concepts, unnecessary additions, missing necessary concepts and unresolved background. A factual association such as “ammeter measures current” is not automatically a pedagogical prerequisite. Never infer a curricular gap from a retrieved subset or incomplete earlier-grade corpus.

Report prerequisite set precision/recall only where both necessity and reference completeness are judged resolvable, with numerator/denominator and mapping rationale. Otherwise report counts and uncertainty. Empty predicted sets have undefined precision; an empty necessary reference set has undefined recall. Do not report unexercised prerequisite extraction as successful merely because the factual graph has edges. Full-curriculum adequacy remains separate and may be uncertain for every case.

## Reporting and uncertainty

For each arm, publish counts of COMPLETE, PARTIAL, INCORRECT, ABSTAIN and ERROR across every scheduled family; unresolved references are an additional explicitly counted category. The primary full-correct proportion is COMPLETE divided by all ten scheduled families in each arm, including errors and abstentions. Unresolved references are not certified COMPLETE and remain in that denominator. Also give explicit lower/upper bounds treating unresolved references as all failures/all successes; report agreement over resolvable references only as a separately labeled secondary statistic. PARTIAL is not converted into half a success. Report subpart outcomes descriptively alongside family results.

Primary grounded agreement for vector versus factual-graph arms requires COMPLETE plus ADEQUATE evidence. Its primary denominator is all ten scheduled families, including failed graph arms and unresolved references; give uncertainty bounds separately. Report coverage and agreement conditional on attempted/accepted answers only with explicit denominators; zero coverage gives undefined conditional agreement.

Preserve pairing: report graph-versus-vector wins, losses and ties per family, then per source chapter. At ten convenience-selected families and five contributing chapters, uncertainty is large and interval estimates are exploratory. Report counts and exact denominators before percentages. Any bootstrap intervals follow the already declared chapter-cluster procedure and are not evidence of a powered result. No favorable subset, retry or post-hoc tolerance may replace the frozen run. Costs, timing, extraction failures and zero-expansion cases remain visible regardless of answer quality.

## Complete retained-graph audit

After prediction freeze, inspect every retained model-extracted entity and factual edge from every attempted source graph (bounded by the current five contributing chapters: at most80entities and120edges). Do not sample only apparently good edges. Original native paragraph nodes are source containers, not extracted semantic claims; audit their provenance separately and keep them out of semantic-claim denominators. Count graph-construction failures and empty graphs, and distinguish saved/retained claims from rejected proposals. No model calls or graph corrections may alter this frozen evaluated graph.

For each retained node, read its name, role, entire description and exact cited original excerpt. For each edge, read subject, relation, object, direction, reason, conditions and its own exact cited excerpt. Score `SUPPORTED`, `PARTIAL`, `UNSUPPORTED`, or `UNCERTAIN`: full support requires the entire claim to follow from that excerpt; partial means a material component is supported but another is unstated; unsupported includes contradiction or mere nearby mention without entailment; uncertain covers extraction or interpretation preventing a dependable decision. Do not repair a claim from outside knowledge or a later passage. If multiple earlier passages could support it but its selected excerpt does not, record that as a citation-localization failure rather than silently replacing the citation.

Separately record source/offset/content validity, entity-role correctness, edge endpoint-role compatibility and edge direction. Valid schema or role compatibility alone is not semantic support. Preserve conditions such as fixed temperature; omitting a material condition prevents strict full support. Review all numerical definitions and units explicitly. For every judgment record the exact claim ID, source quote, reason and reviewer identity; freeze reviewers' initial audit files before adjudication.

Report retained-claim support proportions for nodes and edges separately, with all retained claims in the denominator and PARTIAL/UNSUPPORTED/UNCERTAIN explicitly counted. These are **AI audit agreement**, not independently validated precision. A retained claim approved by the pipeline reviewer but judged PARTIAL/UNSUPPORTED/UNCERTAIN in the later audit is a model-review disagreement; call an unsupported one an apparent false acceptance relative to the AI audit, not a proved expert error. Report examples and counts without promoting inter-agent agreement to truth.

Do not report extraction recall, completeness or missing-prerequisite detection accuracy without an exhaustive reference graph. Zero retained claims gives undefined retained-claim support proportion, not100%accuracy. Larger support proportion with near-zero retention is not by itself useful extraction; present coverage, rejection counts and construction failures alongside it.
