## Testing goals
- **Fast feedback**: most changes should validate via hermetic unit tests in seconds.
- **Determinism**: tests must produce the same outcome across machines and reruns; if external services are required, scope them narrowly and document the expectations.
- **Confidence**: every shipped behavior (config parsing, Google Ads integration) needs a corresponding test to catch regressions before production.

## Current test suites
- **Unit tests (`tests/unit/`)**: currently only `test_config_loader.py`, which exercises `ConfigLoader` parsing, customer-id splitting, and query lookup logic without touching the network.
- **Integration tests (`tests/integration/`)**: `test_google_ads_api.py` instantiates a real Google Ads client using `TEST_GOOGLE_ADS_*` env vars and calls `CustomerService.list_accessible_customers`. A passing run proves OAuth credentials (developer token, client id/secret, refresh token) work end-to-end.
- **Env loading**: `tests/conftest.py` adds `app/python-etl` to `sys.path`, loads `.env`, then overlays `.env.test`. Environment variables become global for the entire pytest session; tests must not mutate them or rely on per-test isolation.

## Testing contract
- **Unit tests** cover pure Python components: config parsing, GAQL query generation, serialization helpers. They run under the default marker set (`pytest` without flags) and must not reach the network or mutate the filesystem beyond tmp paths.
- **Integration tests** are marked `@pytest.mark.integration`, call external APIs, and may read/write fixture directories. They must handle missing credentials gracefully (skip/fail with clear guidance) and remain manually opt-in via `pytest -m integration`.
- **Marking & skipping**: every cross-service test must be marked `integration`. Skipping is acceptable only when prerequisites (credentials, network) are absent, and the skip reason must explain how to provide them. Local reproducibility requires documenting required env vars in README/spec.

## Infrastructure & isolation strategy (future)
- When introducing warehouse/state-store components, each integration suite should provision isolated infrastructure per test run (dockerized Postgres/DuckDB, MinIO) so runs are parallel-safe and hermetic.
- Shared mutable state is forbidden; use fixtures that create fresh schemas/buckets and tear them down afterwards.
- Deterministic fixtures (seeded data, fixed timestamps) ensure repeatability; randomization must be explicitly seeded.

## CI guidance
- Separate jobs for unit vs integration tests. Unit jobs run on every change; integration jobs run on schedule or via explicit tag because they consume real API quota.
- Integration runs must monitor Google Ads quota and network stability; consider retries at the CI harness level to handle transient HTTP failures without masking bugs.
- Credentials used in CI should be scoped to dedicated sandbox accounts, stored in the CI secret manager, and rotated regularly. Never reuse production refresh tokens in CI.

## Checklist for new components
- **State store**: add unit tests for schema migrations/ORM models plus integration tests that spin up a disposable DB and verify checkpoint read/write semantics.
- **Warehouse consumer (loader)**: cover transformation logic with unit tests (pure functions) and add integration tests that ingest sample raw files into a temporary warehouse, asserting idempotent behavior.
- **Orchestrator hooks**: unit-test scheduling logic (cron parsing, CLI args) and integration-test end-to-end runs via the orchestrator’s local runner if feasible.
