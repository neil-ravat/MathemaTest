# NCERT fresh feasibility study — results

**This round found no fully correct solution in any arm and does not establish a graph benefit.** It identified failures in native-text ingestion, automatic graph semantics, answering behavior and the evaluation design. The completed results support engineering diagnosis; they do not yet support a paper claiming reliable extraction, improved answers or educational-prerequisite detection.

All judgments are AI-reviewed references and audits, following the user's agent-only preference. No independent human expert labels were obtained. Predictions, initial references, initial scores and disagreements are retained separately.

## Answer results

Ten worked-example families from five NCERT Class 10 chapters were attempted under each of three conditions. Six families were mathematics and four physics. All planned attempts remain in the denominator, including unavailable graphs, contract errors and damaged inputs.

| Arm | Complete | Partial | Incorrect | Abstain | Error | Total |
|---|---:|---:|---:|---:|---:|---:|
| Direct model | 0 | 0 | 0 | 10 | 0 | 10 |
| Vector retrieval | 0 | 2 | 2 | 5 | 1 | 10 |
| Factual graph augmentation | 0 | 1 | 0 | 4 | 5 | 10 |

Both scoring agents independently assigned the same answer category to all 30 outputs. Their evidence categories initially agreed on 22/30; eight disagreements were adjudicated and preserved. Seven concerned whether uncited abstentions should receive an evidence-failure label or no answer-evidence assessment. The remaining disagreement concerned a correctly cited generic rule used with a false problem-specific premise.

The two proof responses counted PARTIAL state the requested ratio and cite the relevant theorem but provide no proof. The remaining partial response computes the correct intermediate image distance of −37.5 cm, then incorrectly gives 18.75 cm as its magnitude, calls the image virtual and omits its size. Partial does not count as half a success. All four model-declared PASS responses failed the full-answer criterion.

Primary grounded success requires COMPLETE plus ADEQUATE source support. Both retrieval arms scored **0/10**. Direct answering has no supplied-source support score. Graph-versus-vector pairing gives zero wins, zero losses and ten ties on this binary metric. The prespecified 10,000 chapter-cluster bootstrap resamples, seed 42, yield [0,0] because every observed difference is zero. **This degenerate interval is uninformative about population equivalence or future success probability.** Ten convenience-selected families and five chapters cannot establish a general performance rate or small comparative benefit. The [0,0] unresolved-reference bounds in the machine summary are observed-data bounds, not confidence intervals: all original references were resolvable.

The direct arm's ten abstentions are also a warning about the baseline itself. Its prompt permitted learned subject knowledge, yet responses repeatedly demanded supplied passages or subject background. On the fully readable AP classification question, it claimed passage IDs were needed to analyze the supplied number lists. These are results for this model under this answer contract, not evidence that the underlying model cannot solve Class 10 problems. The comparison must not be used to claim retrieval superiority over a functioning unconstrained direct-answer baseline.

## Automatic graph audit

| Source chapter | Retained semantic nodes | Retained factual edges | Construction status |
|---|---:|---:|---|
| jemh103 — pair of linear equations | 9 | 6 | Nonempty |
| jemh105 — arithmetic progressions | 6 | 0 | Empty-edge graph |
| jemh106 — triangles | 5 | 1 | Nonempty |
| jesc109 — light/reflection/refraction | 0 | 0 | Rejected: invalid or repeated relationship candidate ID |
| jesc112 — magnetic effects of current | 14 | 2 | Nonempty |
| **Total** | **34** | **9** | **3/5 nonempty sources** |

The 630 native paragraph nodes are source containers and are excluded from semantic-claim denominators. All 630 containers and all 43 retained semantic claims had exact source/offset/content provenance. That mechanical success did not establish semantic support.

A complete Arbok audit followed by root reinspection and explicit adjudication found:

| Cited-excerpt support | Node descriptions | Factual edges |
|---|---:|---:|
| Supported | 14/34 | 0/9 |
| Partial | 13/34 | 1/9 |
| Unsupported | 7/34 | 8/9 |

Node description support and semantic-role correctness are separate. A quoted game price can be supported while the game is incorrectly typed as a physical medium. These are AI audit proportions, not independent expert precision estimates. No exhaustive reference graph exists, so extraction recall is unmeasured. The root reinspection knew aggregate Arbok findings beforehand and is not a fully blinded second graph audit. Initial support labels agreed on 41/43 claims; both agreed on all nine edges.

Clear failures include a person, Akhila, linked by FLOWS_THROUGH to parallel lines, and magnetic field strength linked by FLOWS_THROUGH to copper wire. A source sentence naming a quantity's unit cannot establish that it flows through a conductor. Other nodes contain full definitions supported only by a title or an anaphoric fragment. The separate Mistral support reviewer approved these retained claims. The staged reviewer and role schema therefore did not establish reliable automatic extraction.

The frozen graph arm adds original excerpts through one-hop factual edges. Only two of ten scheduled families received novel graph-expanded context. Four available graph families had final context identical to vector retrieval; the other four scheduled graph families were unavailable because their source graph was empty or failed. The sole graph PASS response had identical context to its vector counterpart and was only a partial proof response. There are **zero accepted educational-prerequisite edges** and no demonstrated prerequisite-detection benefit.

## Source and reference review

Two separate reference passes agreed on all ten intended original answers. Weezing completed A; root substituted for the unavailable Jessie task for B. Root knew aggregate operational statuses but had not opened model-answer text or A's labels. Arbok adjudicated the locked references without reading predictions. All 33 supporting citation entries matched exact earlier-source text and ended before the corresponding target. A minor prerequisite-label correction separated geometric segment addition from the narrower declared arithmetic/algebra background.

Original PDF pages were inspected with rendered images. Findings were preserved without changing model inputs or rerunning cases:

- FRESH-03: the AP numerators were missing/reordered. The intended sequence is recoverable from the PDF, but the raw model input is materially insufficient.
- FRESH-10: the essential electron-velocity and magnetic-field arrows were absent. Abstaining from that text-only input can be appropriate even though the primary operational result is not a solved original question.
- FRESH-02, 05 and 06: fractions or mathematical glyphs were flattened. The geometry figures in 05/06 are redundant given the recoverable incidence/parallelism statements; they differ from the essential diagram in 10.
- FRESH-09: a neighboring figure caption entered the question text, but the intended question remained recoverable.
- FRESH-01, 04, 07 and 08: question text was faithful.

No question was removed after viewing outcomes. Complete prior-grade curriculum was not supplied, so all ten curriculum-adequacy judgments remain UNCERTAIN_CONTEXT. No missing-prerequisite precision/recall or curricular-error rate is reported.

## Errors, cost and timing

Four graph attempts failed before an answer call because construction was empty or rejected. One additional graph response and one vector response failed the answer/evidence contract. A vector FAIL_LOGIC response incorrectly treated missing retrieved information as a demonstrated contradiction.

| Measurement | Graph construction | Answer comparison |
|---|---:|---:|
| Local model HTTP calls | 13 | 26 for 30 scheduled attempts |
| Prompt tokens | 66,380 | 25,617 |
| Output tokens | 8,199 | 3,966 |
| Model-request wall time | 1,910.1 s | 398.9 s |

Total recorded local inference: **39 calls, 91,997 prompt tokens, 12,165 output tokens and 38.5 minutes of request wall time**. This excludes historical development attempts, source-ingestion setup, unmeasured agent annotation/orchestration costs and the user's pause. Construction is shared preprocessing for both retrieval arms because both use native paragraphs plus automatic entity excerpts; it is not a raw-paragraph-only vector baseline. Construction alone amortizes to 191.0 seconds per selected family in this ten-family run, including failures.

Median per-attempt solve latency, including shared vector search where applicable: direct 10.79 s, vector 18.07 s, graph 10.66 s. The graph median includes four attempts with no model call; over its six called cases the median is 15.22 s. These are not evidence that the graph is faster at solving questions. Model/cache state, different actual context sizes, failed coverage and a three-hour pause between phases limit timing comparisons. Electricity, hardware cost and peak memory were not measured.

## Design and reproducibility limits

The original proposed 60-family study was not completed. A predeclared first-two-worked-examples rule produced ten families; one of six reserved chapters yielded none and was not replaced. This is a bounded convenience feasibility study, not an external preregistration or powered confirmatory sample.

Graph construction saw each chapter through its last selected target start. It could therefore see the earlier target and its worked solution when choosing entities and graph structure. Later evidence cutoffs cannot undo that influence. Both retrieval arms share the affected index. **This run is not a clean target-blind temporal evaluation.** The issue was disclosed before outcome inspection; the original run was preserved rather than silently changed.

Execution checks found matching frozen code, case bytes and Qwen/Mistral weight digests across phases. The reranker was revision-pinned. MPNet was loaded from an offline model-name cache; its actual revision and file hashes were recorded after inference began, which is not a retrospective pre-run pin. A stopped-process copy of the evaluated Chroma store is included in the prediction lock. Predictions, references, reviewer scores, graph audits and adjudications have separate artifacts and hashes. Public NCERT material may have appeared in model training, and agents share model-family biases.

The matched retrieval comparison isolates one-hop factual expansion under the same seed pool, reranker and final context budget. It does not evaluate the full MathemaTest curriculum auditor, MCQ generator or Lean pipeline.

## Readiness decision

The evaluation machinery and an auditable failure analysis are now available. The original five readiness goals remain uneven:

| Goal | Current result |
|---|---|
| Reliable automatic graph extraction | **Not established**; semantic failures remain despite a completed pipeline |
| Ground truth | Ten original cases separately AI-reviewed and adjudicated; **not independent expert gold** |
| Frozen protocol and fresh cases | Executed and preserved; input defects and structural exposure limit validity |
| Fair baselines and ablations | Matched retrieval mechanics implemented and run; direct over-abstention and shared graph-informed index constrain interpretation |
| Accuracy, uncertainty, failure and cost evidence | Complete for this ten-family diagnostic; **insufficient for broad effectiveness claims** |

Before a stronger study: repair notation/diagram ingestion on exposed development cases; replace incorrect role/edge generation and require adequate claim-local evidence; calibrate the answer contract so direct answering can use its allowed knowledge and proofs must contain reasoning; construct graphs before the earliest evaluated target or separately per target; then lock a new unseen evaluation set and a genuinely raw-text retrieval baseline. Do not relabel or rerun these ten families as fresh tests after tuning.

## Files

- Adjudicated answer/support summary: `artifacts/ncert_fresh_output_review_v1/summary.json`
- Initial and adjudicated output reviews: `artifacts/ncert_fresh_output_review_v1`
- Locked AI references and source review: `artifacts/ncert_fresh_ai_review_v1`
- Raw prediction run and prediction lock: `artifacts/ncert_baselines/20260920T182229810602Z`
- Adjudicated full graph audit: `artifacts/ncert_baselines/20260920T182229810602Z/graph_audit_adjudicated.json`
- Construction run, including failures: `artifacts/ncert_study_corpus/20260920T144038507430Z`
- [Execution-integrity review](docs/ncert_execution_integrity_review.md)
- [Scoring rubric](docs/ncert_ai_scoring_rubric_v1.md)
