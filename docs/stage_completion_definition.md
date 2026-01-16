# Stage Completion Definition

A stage is only complete when **all** of the following hold:

1. CLI entrypoint (`gads-etl`) installs and runs (`uv run gads-etl --help`).
2. `pytest` succeeds (unit + integration markers respected) with no unexpected skips.
3. All Python modules import cleanly (no `ModuleNotFoundError`, no syntax errors).
4. `uv run gads-etl daily` executes the happy-path without crashing under nominal config.
5. No semantics from future stages were introduced; only the scoped stage is modified.
6. Repository integrity checks (scripts/check.sh + scripts/verify_repo_integrity.py) pass locally and in CI.
7. Documentation/specs reflect the implemented work.

If any condition fails, the stage remains **incomplete** and additional work/spec updates are required.
