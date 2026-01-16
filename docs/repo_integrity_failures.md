# Repo Integrity Failures

## What broke
1. `raw_sink_object.py` contained literal patch markers (`*** End of File`), causing `SyntaxError` during CLI execution (`uv run gads-etl daily`).
2. `pytest` could not import `gads_etl` because imports were not validated after restructuring, leading to runtime `ModuleNotFoundError`.
3. MinIO-oriented tests inherited the same import failure, masking storage issues.

## Why it was allowed to land
- No automated compile/import check existed after agents generated code.
- Stage completion criteria did not require `gads-etl` or `pytest` to run before merging.
- Control-plane specs did not mandate repo-level integrity scripts, so invalid syntax passed code review.

## Missing invariants
- “Repo must remain runnable” was implicit, not enforced.
- No script verified that all critical modules import successfully.
- Stage completion lacked explicit requirements (CLI/pytest/imports) leading to partial implementations.

## Remediation
1. Added `scripts/verify_repo_integrity.py` to import-check core modules, ensuring syntax/import issues fail fast.
2. Added `scripts/check.sh` to run py_compile, pytest, CLI help, and integrity verification so future agents must keep the repo runnable.
3. Introduced `agents.md` and `docs/stage_completion_definition.md` to codify stage discipline, spec-first expectations, and “do not touch” rules.
4. Documented storage realism and retry/control-plane specs earlier; now failures must be diagnosed and prevented via docs.

With these controls, invalid syntax or broken imports will fail `scripts/check.sh` immediately, preventing regressions before stage completion.
