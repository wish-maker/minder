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

A few config dirs still live **here** under `compose/` as `./`-mounted sources, pending
their tracking issues — they migrate to `../services/` as each resolves (see #23):

| Path | Issue |
|------|-------|
| `rabbitmq/definitions.json` | #27 (stale export, unsafe to load as-is) |
| `traefik/dynamic/` | #25 (dynamic/access-mode feature is half-built) |

For the platform/service overview, see the repo-root `CLAUDE.md`.
