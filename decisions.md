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
