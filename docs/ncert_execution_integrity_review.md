# NCERT execution integrity review

Weezing reviewed configuration, code, manifests and byte hashes on 20 September 2026 while baseline execution was still in progress. No fresh question, source body, reference answer, generated answer or semantic graph claim was inspected. This is an execution audit, not a finding of model correctness or a completed prediction freeze.

Construction run: `artifacts/ncert_study_corpus/20260920T144038507430Z`. Baseline run: `artifacts/ncert_baselines/20260920T182229810602Z`.

## Integrity checks

- All 36 entries in the pre-execution configuration lock match the current files. This is 36 locked files, including code, candidate inputs and the execution amendment; it is not 36 Python files.
- Both run directories contain 33 Python source snapshots; each snapshot matches its corresponding current source file. The construction snapshot contains the builder and the baseline snapshot contains the baseline runner.
- All 94 hashes in the construction artifact lock match. That lock was recorded at 15:13:36 UTC. The mutable Chroma binary store is explicitly excluded; logical inputs and extraction snapshots are retained. Hash integrity alone does not establish equivalence of an unsealed database state.
- The selection lock's four hashes match. The current candidate file and both run copies have SHA-256 `2ed2031fee4996e91ad486bceddd5f7bbaca1363258a58a23d82ee9a76fc0f22`. The baseline case list matches the ten selected IDs. Six reserved chapters yielded five contributing chapters; jesc110 yielded zero selected examples. The first-two convenience amendment supersedes the proposed 60-family random sample for this run.
- Every hashed document in the comparative protocol, factual amendment, scoring, execution and structural-exposure locks matches. The earlier protocol is preserved; its prerequisite-only graph description is superseded by the factual amendment, and its reference-before-inference timing is superseded by the feasibility amendment.
- Construction settings equal the frozen construction settings; baseline settings equal the frozen baseline settings. No configuration drift was found in these records.

## Models and matched conditions

Construction `models.json` and baseline `model_inventory.json` contain identical weight digests:

| Role | Model | SHA-256 digest |
|---|---|---|
| Extraction producer and baseline answering | qwen2.5-coder:7b | dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364 |
| Construction support reviewer | mistral:latest | 6577803aa9a036369e481d648a2baebb381ebc6e897f2bb9a766a2aa7bfbc1cf |

Construction uses context 32,768, output cap 5,000 and HTTP timeout 900 seconds. Baseline answering uses context 16,384, output cap 1,500 and HTTP timeout 240 seconds. Both use native Ollama requests, temperature 0, seed 42 and no corrective retries. The differing construction and answering capacities were declared before fresh inference, not introduced in response to fresh outcomes.

The baseline code computes one eight-candidate vector seed pool per case and shares it between retrieval arms. Both use the same reranker, at most four whole passages and a 6,000-character evidence budget. They share original paragraphs plus automatic entity excerpts; this is vector retrieval over a graph-informed index, not a raw-paragraph-only baseline. Factual graph retrieval augments those seeds by one hop, retains original edge direction and original excerpts, and checks source IDs, offsets and source-text equality. Failure of graph construction is recorded under the no-fallback policy. Direct answering receives no passages and may use learned knowledge, making it a secondary answer comparator with different evidence availability. Arm order rotates by case index. Equal character ceilings do not imply equal actual prompt tokens.

The reranker record pins `cross-encoder/ms-marco-MiniLM-L-6-v2` revision `233902d25c440f23af6f7d6e94d2946bac0bee0a`; baseline code loads that local snapshot on CPU. MPNet embedding code instead loads `sentence-transformers/all-mpnet-base-v2` by model name in offline mode. At this audit, its sole local snapshot and main ref are `e8c3b32edf5434bc2275fc9bab85f82640a19130`. The execution lock does not separately pin or hash embedding weights. Shared offline cache and code support consistency, but this is a reproducibility gap relative to the original request for exact embedding digests. The separate `artifacts/ncert_embedding_integrity_poststart.json` records the current cached revision and per-file SHA-256 hashes without changing the runtime or downloading files. This observation is retrospective metadata, not a new pre-execution lock. Both retrieval arms share the query embedder and index; the missing pre-run pin limits reproducibility rather than establishing unequal arm conditions.

The baseline began at 18:22:29 UTC, over three hours after construction completion/locking, following the user's pause. Inventories show unchanged model digests across the phases. The pause and model loading/cache state can affect latency; timing is local operational measurement, not a controlled hardware benchmark. The digest inventories are snapshots, not continuous attestation that a model tag never changed between individual calls.

## Timing and remaining limitations

The execution amendment was frozen at 14:40:15 UTC, before construction started at 14:40:38 UTC. The scoring lock was recorded at 14:41:09 UTC, during construction but before comparative answer prediction inspection; the factual amendment also records its scoring hash at 14:40:31 UTC. The structural exposure disclosure was recorded at 14:42:14 UTC during construction. These timings must not be described as an external preregistration of every document before all model calls.

The declared graph prefix reaches the last selected target start in each chapter. For an earlier target, that lets graph construction see the target and its worked solution. Later retrieval cutoffs prevent direct future-excerpt delivery but cannot remove effects on entity selection, descriptions or graph topology. Both retrieval arms share the affected index. This run is therefore a factual augmentation diagnostic, not a clean target-blind temporal evaluation. Retain the exposure flags, cases, errors and original graphs; do not retrospectively remove affected targets.

Transcription QA and reference review are deliberately postponed until all scheduled predictions are frozen. Current input fidelity is not yet established. The baseline manifest schedules 30 arm attempts; this does not promise 30 HTTP calls because unavailable arms can fail before inference. At audit time, no completed prediction lock was verified, and no claim is made here about final attempt counts, outcome agreement, citation support or extraction reliability.

The next gate is to finish and hash all scheduled attempts, then create prediction-blind source packets for separate AI reviewers. Freeze their initial references before adjudication and expose shuffled outputs only afterward. All resulting labels remain **AI-reviewed reference agreement, not independent expert accuracy**. The ten convenience-selected families, five contributing chapters, shared agent biases, possible pretraining exposure and graph structural exposure limit generalization. No accepted educational prerequisite graph is being evaluated.
