# `scripts/setup/` — the setup CLI

Native-Python implementation of Minder's installer/lifecycle CLI, invoked as
`python -m scripts.setup <verb> [flags]`. `setup.sh` at the repo root is a thin
shim that execs this — `bash setup.sh <verb>` and `python -m scripts.setup <verb>`
are equivalent.

- **Using it** (install/start/stop/backup/etc.): see
  [Installation](../../docs/getting-started/installation.md) for the full command
  reference, and [Development Guide](../../docs/development/development.md) for the
  dev workflow.
- **How it's organized** (one module per verb, `config`/`docker`/`log` as shared
  foundations): read the module docstrings — they're the source of truth for
  behavior.
- **History of the bash → Python port, and the behavior-gate methodology
  (`scripts/gate/`) that verified it**: see
  [docs/development/setup-cli-migration.md](../../docs/development/setup-cli-migration.md).
  `setup.bash.sh` + `scripts/lib/*.sh` are kept solely as that gate's frozen
  reference — not part of the runtime path.
