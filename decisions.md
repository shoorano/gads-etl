### 2024-06-01 — Status: Accepted
**Context**: `pyproject.toml` requires Python 3.12+ and depends on `google-ads>=24.1.0`.  
**Decision**: Standardize the codebase on Python 3.12+ and the official Google Ads Python SDK.  
**Consequences**: Runtime environments must provide Python 3.12 and support building google-ads dependencies; alternative SDKs are out of scope.

### 2024-06-01 — Status: Accepted
**Context**: Configuration is defined in `config/google_apis.yaml` and secrets live in `.env` / `.env.test`, validated via Pydantic.  
**Decision**: Use typed YAML for declarative settings and load secrets exclusively from environment variables.  
**Consequences**: All new settings must be added to the YAML + Pydantic models; credentials should never be committed to code or configs.

### 2024-06-01 — Status: Accepted
**Context**: Entry points are Typer commands (`gads-etl daily`, `gads-etl catch-up`).  
**Decision**: Keep the pipeline CLI-driven for orchestration and ad-hoc runs.  
**Consequences**: Scheduler integrations (cron/systemd/orchestrators) invoke the CLI; no alternative entry mechanism is planned.

### 2024-06-01 — Status: Accepted
**Context**: `LocalRawWriter` persists payloads to `data/raw/<query>/<date>/payload.jsonl`.  
**Decision**: Use local JSONL files as the initial raw storage sink.  
**Consequences**: Downstream consumers must read from this file structure until object-store or warehouse sinks are implemented.

### 2024-06-01 — Status: Accepted
**Context**: `tests/integration/test_google_ads_api.py` hits `CustomerService.list_accessible_customers` using `TEST_GOOGLE_ADS_*` env vars.  
**Decision**: Integration tests execute against real Google Ads sandbox accounts using TEST-prefixed credentials.  
**Consequences**: Running integration tests consumes API quota and requires valid sandbox tokens; CI must isolate these secrets.

### 2024-06-01 — Status: Accepted
**Context**: README/infra docs specify Hetzner-style hosts provisioned via Ansible with optional containerization.  
**Decision**: Target production deployments on provisioned servers (Ansible + systemd), keeping containers optional for dev parity.  
**Consequences**: Infra automation centers on Ansible roles/playbooks; container workflows remain auxiliary and not mandatory.

### 2026-01-06 — Status: Accepted
**Context**: Specs mandate a per-run identifier for raw partitions and reprocessing.  
**Decision**: `run_id` is an ISO 8601 UTC timestamp with milliseconds, generated once per pipeline execution attempt; retries/reprocessing produce new `run_id`s except when completing a partial attempt.  
**Consequences**: Tooling must stamp every partition and metadata blob with the attempt’s `run_id`; state/consumers use it to distinguish versions.

### 2026-01-06 — Status: Accepted
**Context**: Raw sink contract requires append-only semantics across sources.  
**Decision**: Raw partitions are immutable in meaning; no overwrites. Reprocessing the same logical slice creates a new `(source, customer_id, query_name, logical_date, run_id)` directory.  
**Consequences**: Monitoring/storage must handle multiple partitions per logical date; cleanup is manual and audited.

### 2026-01-06 — Status: Accepted
**Context**: State store intentionally tracks only touched partitions.  
**Decision**: State is lazy/implicit—absence of a record implies `pending`.  
**Consequences**: Enumerations must treat missing rows as work to do; ingestion tooling creates records only when processing occurs.

### 2026-01-06 — Status: Accepted
**Context**: Coordination relies on a small, consistent status model.  
**Decision**: Valid statuses are `pending`, `success`, `failed`, scoped to `(source, customer_id, query_name, logical_date)`.  
**Consequences**: Writers may not invent new statuses; consumers interpret this tri-state set uniformly.

### 2026-01-06 — Status: Accepted
**Context**: Extractors and consumers must stay decoupled via state.  
**Decision**: Only validators write state records; consumers MUST read state and may only consume partitions marked `success`.  
**Consequences**: Extractors remain stateless; consumers cannot skip state checks even if raw files exist.
