# Google Ads ETL

Production-ready template for extracting Google Ads (and eventually Google Merchant) data daily, storing it efficiently, and exposing the results to downstream dashboards. The goal is to demonstrate strong data-engineering practices while remaining lean enough to run on cost-effective Hetzner hosts.

## Highlights
- **Structured layout** separating application code, infrastructure-as-code, and storage specs.
- **Typed configuration** (`config/google_apis.yaml`) with `.env` driven secrets for rapid environment switches.
- **CLI & pipeline skeleton** ready to plug into schedulers (cron, Airflow, Dagster, etc.).
- **Ansible deployment** for platform-agnostic provisioning with room to evolve into Terraform + container orchestration.

## Directory overview
- `app/python-etl/` – Python package (`gads_etl`) that loads config, runs extractors, and writes raw payloads.
- `config/` – YAML configuration describing API resources, schedules, and storage targets.
- `database/` – Documentation plus starter SQL schema for fact tables / warehouses.
- `docs/` – Architecture notes and future design decisions.
- `infra/ansible/` – Ansible inventory, playbooks, and roles for provisioning Hetzner (or any Linux) hosts.
- `tests/` – Split unit/integration suites to keep local dev loops tight.

## Getting started
1. Create your local env files:
   ```bash
   cp .env.example .env
   cp .env.test.example .env.test
   ```
   Populate `.env` with production/dev credentials plus storage targets, and `.env.test` with sandbox-only credentials that are safe to use in automated integration tests.
2. Review `config/google_apis.yaml` and adjust customer ids, queries, and scheduling knobs. Reference environment variables using `${VAR}` syntax.
3. Install dependencies (with [uv](https://github.com/astral-sh/uv) or pip):
   ```bash
   uv sync
   # or
   pip install -e .
   ```
4. Run the CLI:
   ```bash
   gads-etl daily
   gads-etl catch-up --days 30
   ```

### Generating refresh tokens

Use the helper script to produce OAuth refresh tokens and persist them into your `.env` (or `.env.test`) file:
```bash
uv run python scripts/generate_refresh_token.py --env-file .env
```

Before running the script, create an OAuth client of type **Desktop app** (Installed application) in Google Cloud Console. Desktop clients automatically support loopback redirects, so you only need to add `http://localhost` and `http://localhost:8080/` to the authorized redirect URIs once. If you are reusing a Web application client, double check that those exact redirect URIs exist and give the settings a few minutes to propagate.

The script launches a browser window for consent, prints the token to stdout, and updates the chosen env file (defaults to `.env`). The helper automatically infers which environment variable names to use:
- `.env` → expects `GOOGLE_ADS_CLIENT_ID/SECRET` and writes `GOOGLE_ADS_REFRESH_TOKEN`.
- `.env.test` → expects `TEST_GOOGLE_ADS_CLIENT_ID/SECRET` and writes `TEST_GOOGLE_ADS_REFRESH_TOKEN`.

Override either behavior with `--client-id`, `--client-secret`, or `--env-key` if you need something custom.

## Environment variables
Secrets and deployment-specific settings live in `.env` (ignored via `.gitignore`). Key entries:
- `GOOGLE_ADS_*` – developer token, OAuth client credentials, refresh token, MCC IDs, and customer ids.
- `GOOGLE_MERCHANT_ACCOUNT_ID` – optional Merchant Center id.
- `WAREHOUSE_URI` – SQLAlchemy style connection string for the serving warehouse.
- `DATA_LAKE_BUCKET` – bucket/prefix for raw dumps.
- `STATE_STORE_TABLE` – table that stores pipeline offsets.
- `GADS_CONFIG_PATH` – override configuration file location when needed.

Provide both production (`GOOGLE_ADS_*`) and sandbox/test (`TEST_GOOGLE_ADS_*`) credentials so that day‑to‑day ETL runs stay isolated from the integration tests. The `.env` file should contain production/dev secrets, whereas `.env.test` only stores the sandbox credentials. The test credentials should point at a Google provided test account (per the [CustomerService.list_accessible_customers](https://developers.google.com/google-ads/api/reference/rpc/latest/CustomerService) example) so the checks remain harmless.

## Testing
Install the dev dependencies so pytest is available:
```bash
uv sync --extra dev
# or
pip install -e ".[dev]"
```
If you see `ModuleNotFoundError: No module named 'dotenv'`, it means dependencies have not been installed; rerun one of the above commands.

Two logical suites keep the feedback loop short:
- **Unit tests** (default): `uv run pytest` – fast checks that validate config parsing and helper utilities.
- **Integration tests** (hit Google Ads API): `uv run pytest -m integration`

Pytest automatically loads `.env` and, if present, overlays `.env.test`. The integration test in `tests/integration/test_google_ads_api.py` builds a Google Ads client using the `TEST_GOOGLE_ADS_*` environment variables defined in `.env.test` and calls `CustomerService.list_accessible_customers`. A passing run proves that OAuth credentials, developer token, and account permissions are all wired correctly.

## Infrastructure
`infra/ansible` contains an initial Hetzner-friendly bootstrap playbook that:
- Creates `/opt/gads-etl` and supporting directories.
- Installs Python, git, rsync.
- Drops a secure placeholder for the `.env` file (you should later source from Vault or a secret manager).

Extend the playbook with roles for Docker, systemd timers, or other platform specific logic. Because everything is plain Ansible, you can easily pivot to Terraform + Ansible or container-native deploys once requirements solidify.

## Database & storage
See `database/README.md` for the proposed two-layer approach (raw object store + curated warehouse). `database/schema/warehouse_tables.sql` contains canonical fact tables for campaign and ad group metrics; adapt this file or replace it with migrations as the model evolves.

## Next steps
- Flesh out Google Ads extractors with batching, partition checkpointing, and schema-aware loading.
- Add orchestration (Prefect, Dagster, Airflow) and wire to the CLI commands.
- Introduce proper secret management (Vault, SOPS, AWS/GCP Secret Manager) and integrate with the Ansible roles.
