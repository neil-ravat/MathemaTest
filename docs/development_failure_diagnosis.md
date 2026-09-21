# Development failure diagnosis

Inspected on 2026-09-20. This audit covers the frozen 48 development cases, saved 192 development responses, saved 28 gate responses, generator, payload builder, decoder, and score calculation. It makes no new model calls and does not inspect held-out case contents. The ponytail skill was applied to keep the audit focused on existing evidence.

Reproduce the label, payload, hash, and score checks with `.venv/bin/python scripts/audit_development_labels.py`. The script is read-only and uses the historical run IDs below.

## Evidence integrity and labels

- Development run: `artifacts/controlled_study/20260917T201622567827Z`.
- Gate run: `artifacts/controlled_study/20260917T201302167860Z`.
- Both prediction SHA-256 values match their respective `COMPLETE.json` records.
- All 192 saved development payloads exactly match the current complete-context payload builder. All are marked complete; none contains a future passage. The failure cannot be attributed to top-k omission in this run.
- A separate read-only Python check parsed the visible `Define ...` text and target equalities with Python AST, recursively evaluated only addition and available function definitions, and classified previews directly. It did not use `oracle.nodes`, `oracle.claim`, or `required_ids`. Its results agree with all 48 development labels. This is a check of the narrow constructed task, not independent textbook annotation.
- The expected class distribution is 24 PASS, 16 FAIL_GAP, and 8 FAIL_LOGIC. The always-PASS baseline is therefore 24/48.
- There are only 40 unique complete-context payloads: each family's missing and future variants become identical after inadmissible future content is removed. Preserve all 48 predeclared cases in the primary score, disclose this redundancy, and retain family-level uncertainty estimates. Missing versus future performance cannot be interpreted as separate capabilities in this arm.

## Recomputed outcomes

| Model | Prompt | Exact matches | Schema errors | Missing/future matches | False-equality matches |
|---|---|---:|---:|---:|---:|
| Qwen | Original plus contract | 17/48 | 20 | 0/16 | 0/8 |
| Qwen | Evidence | 13/48 | 0 | 0/16 | 3/8 |
| Mistral | Original plus contract | 17/48 | 0 | 0/16 | 5/8 |
| Mistral | Evidence | 8/48 | 0 | 2/16 | 3/8 |

All 20 Qwen original schema errors omit `cited_passage_ids`. Only one rejected response has the correct raw status; merely ignoring that field would move this score from 17 to 18, still below 24. Do not retroactively relax the primary scoring contract. The original prompt lists a shorter JSON schema before the appended citation contract, which may contribute to omissions; the evidence prompt avoids that duplicated schema. This is a plausible prompt-design contributor, not an experimentally isolated cause.

The saved seven-fixture gate reproduces 2/7 and 4/7 for Qwen original/evidence, and 1/7 and 4/7 for Mistral original/evidence. It remains failed.

## Representative failures traced manually

These examples demonstrate distinct mechanisms; no exhaustive human failure taxonomy is claimed.

1. **Correct calculation, wrong status.** Qwen evidence, supported case `d1bed6e22f187673` (topology-00), calculates `fun0_0(1)=3` and `fun0_1(1)=1+3+2=6`, exactly the claim, but emits FAIL_LOGIC. Conversely, topology-04 false case calculates 26 correctly while the target claims 27, yet emits PASS. Status accuracy alone cannot locate this error.
2. **Recognized missing premise, wrong class.** Qwen evidence, missing case `f18f633f5ffd76c2`, explicitly says no definition for `fun0_0` exists and lists it as missing, but emits FAIL_LOGIC. Complete context makes the correct class FAIL_GAP. The corresponding future variant has the same admissible input and response.
3. **Unresolved dependency accepted.** Mistral evidence on that missing case recognizes that `fun0_0(1)` is undefined and cannot be evaluated, then calls the equality false while emitting PASS. This combines missing-premise handling with contradiction between explanation and status.
4. **Arithmetic error endorses a false claim.** Mistral evidence, false case `485960917a113b11`, says `1 + (1+1+1) + 2 = 7` and emits PASS. The expression equals 6. This cannot be repaired by only remapping labels.
5. **A worked example is incorrectly required.** Mistral original on `d1bed6e22f187673` says applying the supplied definition at argument 1 is not provided in context. The definitions and allowed integer arithmetic already suffice. Qwen original makes the same kind of demand.
6. **Background handling fails.** Mistral evidence classifies seven of eight background cases FAIL_GAP even though the removed prerequisite is explicitly present in `background_passages`. Qwen evidence misclassifies all eight as FAIL_LOGIC. Background passages must participate in dependency evaluation, not merely citation validation.
7. **Preview rule is ignored.** Mistral evidence abstains on all eight previews, despite the system instruction that an explicit preview requires no proof and should pass. Both original-prompt models pass all eight previews.
8. **Correct status can hide incorrect reasoning.** Mistral original on false case `485960917a113b11` emits the correct FAIL_LOGIC label, but explains that substitution is unavailable rather than identifying the numerical discrepancy. The current label score rewards this outcome; it does not establish sound evidence.

## Scoring and experiment limitations

No wrong development labels or historical exact-match counting bug was found in the inspected scope. Invalid outputs remain in the denominator as intended. However, the decoder checks citation membership and the completeness restriction, not whether a citation supports the reasoning or whether the explanation agrees with the status. A missing background citation can pass even when that passage was mathematically necessary. A valid JSON object is therefore insufficient evidence of reliable judgment.

The fixed oracle label describes the full admissible curriculum. In a future incomplete-retrieval arm, ABSTAIN can be the correct evidence-limited behavior while still counting as a mismatch against that full-curriculum label. Such a score should be called full-curriculum exact match and reported alongside coverage and evidence-conditioned behavior. It is not a bug affecting this complete-context development comparison.

## Implications for the focused revision

Require structured intermediate evidence that distinguishes preview, missing dependencies, and evaluable equalities. Include both context and background in the admissible evidence. Separate the numeric calculation and missing-definition result from final status selection, with a deterministic status mapping once evidence has been validated. Keep arithmetic correctness separate from status consistency; a consistent wrong calculation must still fail the benchmark. Do not infer or repair verdicts using keywords in free-form reasons.

Evaluate every one of the same 48 cases under the fixed revised protocol and both models. Preserve raw outputs and errors, compare against both historical prompts and the 24/48 baseline, and disclose development tuning. If symbolic code performs evaluation, describe the result as a hybrid system rather than improved unaided LLM reasoning. No result here supports opening held-out inference before a fresh identical-code gate passes, or claims about natural textbook defects.
