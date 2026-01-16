# Agent Contract

## Project definition
Production-grade Google Ads ETL pipeline that extracts GAQL data into immutable raw partitions, stores state/authority separately, and exposes control-plane commands plus validator/consumer contracts.

## Locked architectural invariants
- Raw partitions identified by (source, customer_id, query_name, logical_date, run_id) and sealed via metadata.json.
- run_id fences every execution attempt; reprocessing always emits a new run_id.
- Raw data is immutable once metadata.json exists; no overwrites.
- PartitionState is the sole authority for consumers and control-plane actions.
- Validators alone set status=success/failed; control-plane commands only toggle pending/failed metadata.
- Sink selection is configuration-driven (filesystem vs object storage) with identical semantics.
- Packaged CLI execution model is locked: all commands run inside the activated `.venv`, editable install is mandatory, pytest must be invoked as `python -m pytest`, `uv run` is forbidden, and no sys.path/pythonpath hacks are allowed.

## Stage discipline rules
- Every change must declare the active stage and stay within its scope.
- Earlier stages are locked; do not modify Stage 1–10 semantics without an approved spec.
- Future stages require specs before code; no speculative plumbing.

## Allowed actions for agents
- Implement tasks explicitly described in a stage spec.
- Modify code/config/docs necessary to satisfy acceptance criteria.
- Add tests/scripts enforcing locked invariants.

## Forbidden actions
- Editing locked stages without a spec.
- Introducing new architecture, sinks, or control-plane behaviors not in scope.
- Touching validator/state semantics unless explicitly asked.
- Leaving the repo non-runnable (broken CLI, failing pytest, import errors, syntax errors).

## Treating future stages
- Future stages are placeholders; do not preemptively implement them.
- Specs must precede implementation; once a spec exists, follow it exactly.

## Spec-first interpretation
- For any new behavior, add/update documentation/specs before writing code.
- Specs must describe intent, invariants, and acceptance criteria; code implements only what the spec states.

## “Do not touch” definition
- Areas marked locked (stages, invariants, files) are read-only unless a new spec explicitly reopens them.
- Do not rename/move/remove locked artifacts.

## Repo stability requirement
- The canonical dev loop is venv-based: `uv venv`, `source .venv/bin/activate`, `pip install -e .` (once), then run `pytest`, `gads-etl`, etc. Editable mode means subsequent code edits are live; do **not** reinstall on every change. `uv run` is unsupported because it bypasses the editable install.
- After each change: CLI entrypoint works, `pytest` passes, imports resolve, `gads-etl --help` works, and scripts/dev_check.sh plus scripts/verify_repo_integrity.py pass inside the activated venv.
