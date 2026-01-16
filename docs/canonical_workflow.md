# Canonical Workflow

This repository uses a packaged-CLI execution model. To avoid import drift, every developer must follow the same venv-driven workflow:

1. Create and activate the venv once:
   ```bash
   uv venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```
2. During daily work, keep the venv active and run tools via the installed package:
   - `python -m pytest`
   - `gads-etl <command>`
   - `./scripts/dev_check.sh`

Editable install means code edits are live; no reinstall per edit.

`uv run` and sys.path/pythonpath hacks are forbidden because they bypass the editable install and cause import/CLI divergence. This discipline prevents broken packaging and ensures every stage stays runnable.
