# Ansible deployment

This directory bootstraps the infrastructure that will run the Google Ads ETL.

## Layout
- `playbooks/` contains reusable entry points (`bootstrap.yaml` creates users, packages, and file system layout).
- `inventories/` holds static inventory examples. Replace with dynamic inventory when wiring Hetzner.
- `group_vars/` captures deployment wide defaults (paths, Python version, env file locations).
- `roles/` is where idempotent configuration modules live. Start with `common` for the base host prep.

## Usage
```bash
ansible-playbook -i inventories/dev/hosts.ini playbooks/bootstrap.yaml \
  -e env_file=/etc/gads-etl/.env
```

Keep playbooks OS agnostic by avoiding distribution specific modules whenever possible. Platform specific logic should sit inside dedicated roles guarded by `ansible_facts` conditionals.
