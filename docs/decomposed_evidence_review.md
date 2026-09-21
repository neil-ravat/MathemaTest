# Evidence review of the decomposed development run

Run: `artifacts/controlled_study/20260919T223749942686Z`.

Status: final review of the completed 96-row development run, 48 rows per model. The prediction SHA-256 is `756d3bb50a9972bff89f864784390c5124457c479ffb2c6fbcdeadaa3fdaae1b`, independently recomputed and matched to `COMPLETE.json` (96 calls, 96 rows). No inference code or decision rule was changed. No held-out cases were inspected.

The review uses the independent visible-text evaluator in `scripts/audit_development_labels.py`. To check a recorded computed number, it substitutes that number into a copy of the visible target and independently checks whether it follows from the supplied definitions. Oracle nodes, oracle claims, and required-ID metadata are not used to determine source correctness. The labels remain scored under the original protocol; this is a supplemental evidence audit.

## Qwen: calculation validity differs from label accuracy

| Observation | Count |
|---|---:|
| Correct final labels | 29/48 |
| Accepted numeric calculations | 28 |
| Numeric calculations matching the visible source | 11 |
| Wrong numeric calculations despite available definitions | 11 |
| Numeric calculations despite a missing required definition | 6 |
| Correct labels accompanied by a wrong computed result | 4 |
| Reported missing prerequisites | 6 |
| False missing-prerequisite reports | 0 |
| Literal-only calculation strings | 0 |
| Rejected calculations containing unexpanded function calls | 6 |

All four correct labels with wrong calculations are false-equality cases: rejecting a false claim does not require producing the correct result, so an unrelated wrong result can still earn label credit.

| Family | Claimed value | Recorded computation | Value from visible definitions | Final label |
|---|---:|---:|---:|---|
| topology-00 | 7 | 8 | 6 | FAIL_LOGIC |
| topology-02 | 19 | 21 | 18 | FAIL_LOGIC |
| topology-03 | 23 | 18 | 22 | FAIL_LOGIC |
| topology-06 | 15 | 22 | 14 | FAIL_LOGIC |

For topology-00, the expression `(1 + (1 + 1 + 1)) + 2 + 2` adds an extra 2. The calculator accurately evaluates that incorrect substitution to 8. Thus the deterministic calculator fixes evaluation of the expression, not the model's translation of definitions into that expression.

For topology-02 missing/future, the model explains that the undefined `fun2_0(3)` can be treated as a placeholder that does not affect the result, then returns a fully numeric expression. The dependency does affect the result. Membership-valid citations do not detect the invented substitution. Topologies 03 and 07 similarly produce numbers despite missing definitions, giving six such rows in total.

The six missing-prerequisite reports occur in the missing/future variants of families 00, 01, and 04. Each correctly identifies the absent first function; no invented missing premise was observed in this subset. This is an observed result, not a guarantee that the protocol prevents invented absences.

No response used a bare integer calculation, so the known claim-copying vulnerability was not observed in that simple form. Numeric agreement does not prove faithful substitution: different incorrect expressions can agree at the single tested input. These checks therefore establish numerical agreement only, supplemented by the traced examples above.

The revised model's 29 correct labels include four with demonstrably wrong calculations. The primary score must remain 29/48, accompanied by this limitation rather than relabeled as 29 supported derivations. The protocol is calculator-assisted model judgment, not source-grounded proof.

## Mistral: missing dependencies and substitutions remain unresolved

| Observation | Count |
|---|---:|
| Correct final labels | 16/48 |
| Accepted numeric calculations | 29 |
| Numeric calculations matching the visible source | 6 |
| Wrong numeric calculations despite available definitions | 17 |
| Numeric calculations despite a missing required definition | 6 |
| Correct labels accompanied by a wrong computed result | 4 |
| Reported missing prerequisites | 0 |
| False missing-prerequisite reports | 0 |
| Literal-only calculation strings | 0 |
| Validation errors | 13 |

The 13 errors comprise ten calculations retaining function calls, two previews with forbidden non-null calculations, and one calculation string containing `= 10` rather than an expression. All stay in the primary denominator. The absence of false missing reports is uninformative here: Mistral reports no missing prerequisites at all, including all 16 missing/future cases. Six of those cases receive invented numeric substitutions; the remaining ten fail expression validation.

| Family | Claimed value | Recorded computation | Value from visible definitions | Final label |
|---|---:|---:|---:|---|
| topology-03 | 23 | 16 | 22 | FAIL_LOGIC |
| topology-04 | 27 | 37 | 26 | FAIL_LOGIC |
| topology-06 | 15 | 11 | 14 | FAIL_LOGIC |
| topology-07 | 26 | 32 | 25 | FAIL_LOGIC |

These four correct labels use wrong computations. In topology-04, the model duplicates `fun4_0(5)`: its expression is `(5 + 5 + 1) + ((5 + 5 + 1) + (5 + 5 + 2) + 3)`, giving 37 instead of 26. The erroneous result still differs from the false target 27 and receives a correct label.

The reverse also happens: topology-05 false produces `(3 + (2 + ((1 + 1 + 1) + 1 + 1)) + 1)`, which evaluates to the claimed 11 rather than the source-derived 10, so the calculator returns an incorrect PASS. This demonstrates that nontrivial expression text can still endorse a false target; zero literal-only expressions does not establish protection against claim influence.

The topology-01 background case has a correct calculation and PASS, but cites only `fun1_0` although its reason and calculation also use `fun1_1`. Citation membership validation does not require complete evidence attribution. Numerical checks should therefore not be described as full evidence verification.

## Supported next step

Keep the primary scores at Qwen 29/48 and Mistral 16/48. Across the two models, eight correct FAIL_LOGIC outcomes contain incorrect calculated values. This supplemental observation does not retroactively redefine accuracy, but prevents interpreting correct labels as sound derivations.

The next development intervention supported by the errors is checking dependency extraction and substitution against the supplied definitions before accepting a numerical expression. Arithmetic evaluation alone is insufficient. For this narrow grammar, a source-based symbolic evaluator can serve as a transparent diagnostic or baseline; using it inside the tested system would be an explicitly changed hybrid method and would not establish general textbook understanding. Alternatively, model-produced structured definition/step evidence could be checked locally. Choosing and declaring that revised method belongs to a subsequent frozen experiment, not a repair of these saved outputs.

No evidence here supports opening held-out evaluation by itself, claiming both models improved, or claiming reliable prerequisite detection. The current gate and model-specific development results must be considered separately. The saved run and all failures should remain unchanged.
