## CI goals
- **Fast**: PRs should receive feedback in minutes; long-running checks belong on nightly jobs.
- **Deterministic**: every job must produce the same outcome when rerun with the same commit and environment.
- **Reproducible**: contributors must be able to run any CI stage locally with a single documented command.

## Pipeline stages
1. **Lint/format** (placeholder) – add once a formatter (e.g., Ruff/Black) is adopted. Runs on every PR commit.
2. **Unit tests** – `uv run pytest` (default marker set). This stage must pass for every PR and enforces hermetic tests only.
3. **Type checks** (placeholder) – reserve a stage for `pyright`/`mypy` when introduced.
4. **Integration tests** – `uv run pytest -m integration`. Runs in a separate job, ideally on-demand (label-triggered) or nightly because it calls real Google Ads APIs and consumes quota.

## Environment & secrets
- CI jobs load `.env`/`.env.test` equivalents via pipeline secrets. Only sandbox credentials (`TEST_GOOGLE_ADS_*`) are injected into integration jobs. Production `GOOGLE_ADS_*` variables must never enter CI.
- Secrets are scoped per job: unit tests do not need Google credentials; integration jobs receive the minimal refresh token/client credentials required for the sandbox account.

## Flake control
- Handle retries at the job level. Integration jobs may rerun once automatically if they fail with known network/quota errors. Do not hide failures via in-test retries unless the SDK exposes built-in semantics.
- If the Google Ads API enforces quota, schedule integration jobs during low-traffic windows or distribute accounts across multiple configs. Failures due to quota exhaustion should fail the job with a clear message.

## Performance guidance
- Cache the uv/pip virtual environment between runs (e.g., cache `.venv` or uv’s directory) keyed by `pyproject.toml`/`uv.lock`. This keeps unit stages under a minute.
- Enable pytest parallelism (`pytest -n auto`) for unit tests once the suite grows, ensuring fixtures stay isolated.

## Local parity
- Every CI command must have a documented local equivalent (README/spec). Contributors should be able to run `uv run pytest` and `uv run pytest -m integration` locally before pushing. If a future lint/type job is added, its command must also be runnable locally without extra tooling.
