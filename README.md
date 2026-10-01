# MathemaTest

MathemaTest is a research prototype for auditing whether textbook tasks are supported by earlier instructional material and declared learner knowledge. It uses existing language models; it is not a separately trained foundation model.

## Current code

This release promotes the implementation from the local `development/repair_20260930` workspace into the normal `src/`, `scripts/` and `tests/` directories.

The curriculum route prepares source-ordered CNXML/MathML records, proposes alternative solution routes, retrieves eligible earlier passages with TF-IDF, checks exact task spans and source witnesses, separates missing task facts from missing instructional rules, and requests a final grounded review. It records supported, review-required and execution-error outcomes. This route does not call Lean or Neo4j.

The separate PDF/graph/numerical route contains native Poppler extraction, Neo4j/Chroma retrieval, quantity and relation guards, and bounded rational arithmetic checks. General curricular accuracy and an advantage from graph traversal have not been established.

## Run the offline checks

The tested local environment is Python 3.12. The lock file records that environment; installing optional ingestion/OCR components from `pyproject.toml` is not required for these regression checks.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-local.lock.txt
.venv/bin/python -m pytest -q
```

PDF integration checks require a separately obtained NCERT PDF and Poppler. They skip when those inputs are absent. Credentials and local services are not needed for the offline regression suite. The regression suite was run locally: 533 passed and 9 skipped. The optional CI workflow is omitted because the upload token does not grant workflow permission.

## Inputs and recorded outputs

- `data/`: constructed curriculum controls, selected NCERT inputs, and pinned OpenStax source records and corpora.
- `artifacts/controlled_study/`, `transfer_diagnostic/`, and `transfer_replay/`: earlier controlled inputs, responses and scoring/replay records.
- `artifacts/book_pilot/`: retained partial book-pilot records, including failures and pending cases.
- `artifacts/groq_development_revision_20261001_01/`: nine development controls, with three supported and six review outcomes.
- `artifacts/groq_fact_taxonomy_validation_20261001_02/`: five selected task-category checks.
- `artifacts/groq_book_transfer_20261001_01/` and `gpu20b_book_transfer_20261001_01/`: saved transfer attempts and the T4 continuation; no GPU or model process starts when these files are opened.
- `artifacts/six_improvements_20261001/`: extraction counts, before/after code and corpora, the incomplete frozen comparison, and subsequent extraction repairs.
- `artifacts/release_manifest.json`: SHA-256 hashes of copied code, inputs and outputs, plus the included and excluded artifact scopes.

These runs have different versions, tasks, labels and denominators. The frozen comparison retains four error outcomes and eight unattempted arms, with no valid final judgments. Incomplete calls are not successful abstentions. Constructed and assistant-reviewed development labels are not independent expert ground truth. The original 30-case/503-item headline data were not recovered and are not recreated here.

Saved records are copied without rewriting their contents. Some contain original absolute local paths; use the corresponding repository-relative files for inspection. Original lock hashes and source snapshots describe their original executions, not a fresh run of the current code. Administrative process snapshots and runtime logs are omitted. The release manifest describes the public subset; it does not claim that every historical local artifact is included.

## Live runs

Use `python scripts/run_gpt4o_smoke.py --help`, `python scripts/run_curriculum_audit.py --help`, or `python scripts/run_book_pilot.py --help` to inspect supported options. Configure credentials locally through environment variables or an ignored `.env`. API access, quota and any paid budget must be supplied separately. Merely publishing the code does not start inference or resume the frozen comparison.

## Data attribution and scope

OpenStax source URLs, revisions, licenses and hashes are retained in the source manifests and source `LICENSE` files. The included Calculus source manifest specifies CC BY-NC-SA 4.0; the Physics source under `artifacts/six_improvements_20261001/physics_source/` specifies CC BY 4.0. Derived text records retain their attribution. These data licenses are separate from the repository's code license. NCERT records are attributed development excerpts; the source PDF is not distributed here.

Research manuscripts, Word/PDF files, API keys, private databases, model weights and local environments are excluded from this update.
