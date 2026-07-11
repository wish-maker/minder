# docker/compose/ — orchestration

This directory holds **how to run** the Minder stack. Per-service **config** lives in
[`../services/`](../services/) — that is the single source of truth for anything mounted
into a container.

## Contents

| File | Role |
|------|------|
| `docker-compose.yml` | The stack definition. **The source of truth — hand-maintained; edit it directly.** |
| `docker-compose.override.yml` | Dev-only convenience (exposes some service ports directly for local testing). |
| `.env` | Runtime env for `docker compose`. **Mirrored** from the repo-root `.env` (the source of truth) on every `setup.sh` run — do not edit here. |
| `README.md` | This file. |

## Editing docker-compose.yml

`docker-compose.yml` is the **hand-maintained source of truth** — edit it directly,
including image tags. Config-file *mounts* should point at `../services/<name>/…`.

> **Note:** image **versions** here are the single source of truth. `versions.sh`
> (image pulling + the `doctor` / `update --check` drift report) reads them straight from
> this file's `image:` lines — `THIRD_PARTY_IMAGE_META` in `scripts/lib/config.sh` now
> holds only per-image resolution *metadata* (stable-track prefix + update constraint),
> not versions. So a version bump is a **one-file edit here**, with no second place to
> keep in sync (#12).

## The compose/ vs services/ split

- **`compose/`** = orchestration (this directory).
- **`../services/`** = all per-service mounted config (postgres init.sql, prometheus,
  grafana, rabbitmq, traefik, ollama init-models.sh, …), mounted via `../services/<name>/`.

`compose/` now holds **no `./`-mounted config sources** — every config mount points at
`../services/<name>/`, so the split above is complete (the last two `./`-mounted dirs
were retired, see #23):

- **rabbitmq `definitions.json`** — no longer mounted. The old export was a stale v3.13
  file with no `password_hash`, and `rabbitmq.conf` has no `load_definitions` directive,
  so the mount was inert and only produced a Docker empty-dir (dangling-source footgun).
  Revisit under #27 if declarative definitions are ever needed.
- **traefik dynamic config** — lives under `../services/traefik/dynamic/`; the
  dynamic/access-mode feature itself is still half-built (#25).

For the platform/service overview, see the repo-root `CLAUDE.md`.
