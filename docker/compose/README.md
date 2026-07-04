# docker/compose/ — orchestration

This directory holds **how to run** the Minder stack. Per-service **config** lives in
[`../services/`](../services/) — that is the single source of truth for anything mounted
into a container.

## Contents

| File | Role |
|------|------|
| `docker-compose.yml` | The stack definition. **Generated** — do not edit by hand. |
| `docker-compose.override.yml` | Dev-only convenience (exposes some service ports directly for local testing). |
| `.env` | Runtime env for `docker compose`. **Mirrored** from the repo-root `.env` (the source of truth) on every `setup.sh` run — do not edit here. |
| `README.md` | This file. |

## Generating docker-compose.yml

`docker-compose.yml` is regenerated from
[`../../.setup/templates/docker-compose.yml.template`](../../.setup/templates/docker-compose.yml.template)
(image versions come from `THIRD_PARTY_IMAGE_SPECS` in `setup.sh`):

```bash
./setup.sh regenerate-compose
```

Make compose changes in the **template**, not in the generated file (the generated file is
overwritten). Config-file *mounts* should point at `../services/<name>/…`.

## The compose/ vs services/ split

- **`compose/`** = orchestration (this directory).
- **`../services/`** = all per-service mounted config (postgres init.sql, prometheus,
  grafana, rabbitmq, traefik, ollama init-models.sh, …), mounted via `../services/<name>/`.

A few config dirs still live **here** under `compose/` as `./`-mounted sources, pending
their tracking issues — they migrate to `../services/` as each resolves (see #23):

| Path | Issue |
|------|-------|
| `openwebui/functions.json` | #24 (invalid JSON + dead config mechanism) |
| `rabbitmq/definitions.json` | #27 (stale export, unsafe to load as-is) |
| `traefik/dynamic/` | #25 (dynamic/access-mode feature is half-built) |

For the platform/service overview, see the repo-root `CLAUDE.md`.
