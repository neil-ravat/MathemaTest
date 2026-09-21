# Connected NCERT engineering smoke — 20 September 2026

**One real connected example completed: Electricity Example 11.1 returned 300 C, with status `ARITHMETIC_CHECKED`.** This is a repaired native-digital-PDF/numerical-question configuration, not the original OCR/calculus/Mathlib configuration or a benchmark accuracy result.

Final run: [20260920T134850055778Z](artifacts/ncert_connected_smoke/20260920T134850055778Z/COMPLETE.json). [Full audit](artifacts/ncert_connected_smoke/20260920T134850055778Z/audit.json) includes the actual messages, retrieved evidence, model response, calculation and compiler result.

## What ran

1. `pdftotext -layout` extracted 226 original text spans from the two pinned NCERT PDFs, covering 35 pages. PDF and extracted-text hashes matched the pinned sources. Exact character offsets and target boundaries were retained.
2. Real Docker Neo4j and Chroma stored the passages, with real MPNet embeddings. Local Qwen2.5-Coder 7B extracted eight entities and four tentative relationships from only the text preceding Example 11.1. Generated descriptions were not substituted for source evidence.
3. Real scoped hybrid retrieval and the cached MiniLM cross-encoder ran for all 12 candidate questions. All returned spans passed source identity and position checks: zero observed violations. These were 12 retrieval checks, **not 12 solved questions**.
4. One numerical audit received the original question and one deduplicated original source span `[0, 4303)`, ending exactly before that question. Its worked solution was excluded. Declared background supplied rational arithmetic, minute-to-second conversion and SI unit operations.
5. The model produced `0.5 * 600`, claimed `300`, and unit `C`. The exact rational checker returned 300. Actual Lean 4.26.0 compiled the generated integer cross-multiplication equality successfully, with no errors or warnings. No model-authored code was executed.

The runtime used local Ollama `qwen2.5-coder:7b`, Q4_K_M, digest `dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364`. Requests, responses, source snapshots, model metadata, retrieval traces and artifact hashes are retained in the run directory. Only two inference calls occurred in this final attempt.

## Development attempts retained

| Attempt | Calls | Outcome |
|---|---:|---|
| `20260920T133912214562Z` | 1 | Unsupported graph labels rejected; no audit. |
| `20260920T134454265032Z` | 2 | Graph succeeded; units embedded in the arithmetic expression were rejected. |
| `20260920T134713688082Z` | 1 | Relationship referenced an absent entity; rejected before auditing. |
| `20260920T134850055778Z` | 2 | Connected example completed with arithmetic checked. |

There were **six inference calls across four engineering attempts**. The final configuration constrains graph labels and numeric expression syntax with JSON schemas, validates relationship endpoints, explicitly instructs matching endpoints, and uses temperature zero/seed 42 in source extraction. These are development changes following observed failures, not a frozen evaluation. Structured generation uses [Ollama's documented schema support](https://ollama.com/blog/structured-outputs); validation remains mandatory.

## Validation and limits

- 65 focused tests passed across digital ingestion, scoped retrieval, numerical auditing, exact arithmetic, schema validation and research-integrity checks. The seven extraction/audit tests also passed after the last prompt/settings change. One pre-existing Pydantic configuration deprecation warning remains.
- Three separate real Lean controls accepted two correct equalities and rejected a false claim. See [compiler controls](artifacts/mathematest_setup/arithmetic_lean_checks/results.json).
- Five separate real-Neo4j synthetic controls passed, including rejecting an earlier ancestor reached through a future intermediate node. See [graph control](artifacts/mathematest_setup/graph_control.json). This is synthetic infrastructure evidence, not NCERT evidence.
- The successful NCERT extraction proposed **no `PREREQUISITE_OF` edges** and returned **zero prerequisite expansions**. It therefore demonstrates service integration, not a useful prerequisite graph or an advantage over ordinary retrieval. Entity evidence uses the entire preceding prefix rather than independently localized concept spans.
- Lean certifies only the generated arithmetic equality. It does not certify the conversion from 10 minutes to 600 seconds, source-to-expression mapping, units, graph semantics or curricular adequacy. `units_verified` and `question_fidelity_verified` remain false. The answer agrees with this previously inspected example; there is no teacher-adjudicated gold audit label.
- Native text extraction does not certify formula typography, tables or diagrams. The original OCR route and Mathlib setup remain incomplete. The legacy chapter-only audit path remains distinct from the new source-position-scoped question path.
- This selected, previously inspected case cannot establish accuracy, generalization or superiority. Earlier direct-model diagnostics and failed integration reports remain unchanged.

## Reproduce and next step

With the local Ollama and dedicated Neo4j services running, execute `.venv/bin/python scripts/run_ncert_connected_smoke.py` from this repository. Each execution creates a new source namespace and artifact directory; it does not clear earlier data. Schema constraints do not guarantee semantically correct model output, and validation may still reject a future attempt.

Next, review and localize the prerequisite graph, freeze this numerical-question protocol, then evaluate the remaining NCERT cases with independent answer/source checks. Compare graph-enabled retrieval with a matching vector-only baseline before claiming a graph benefit.
