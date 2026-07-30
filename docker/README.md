# docker/ — orchestration & service config

This directory holds **how to run** the Minder stack (the compose files) plus, under
[`services/`](./services/), the per-service **config** mounted into containers — the
single source of truth for anything a container reads.

> **Layout flattened in #28:** the compose files moved up from the old
> `docker/compose/` into `docker/` (one less level). The project name is pinned to
> **`minder`** (top-level `name:` in `docker-compose.yml`) so it no longer depends on
> the parent-directory basename — the move would otherwise have renamed every volume
> (`compose_*` → the new dir name). Config mounts now point at `./services/<name>/`.

## Contents

| File | Role |
|------|------|
| `docker-compose.yml` | The stack definition. **The source of truth — hand-maintained; edit it directly.** |
| `docker-compose.override.yml` | Dev-only convenience (exposes some ports directly for local testing). |
| `docker-compose.test.yml` | Isolated dependencies for local integration/e2e tests (CI uses GitHub Actions service containers instead). |
| `.env` | Runtime env for `docker compose`. **Mirrored** from the repo-root `.env` (the source of truth) on every `setup.sh` run — do not edit here. |
| `services/` | All per-service mounted config (postgres init.sql, prometheus, grafana, rabbitmq, traefik + `traefik/dynamic/authelia-forwardauth.yml`, authelia, …), mounted via `./services/<name>/`. |
| `README.md` | This file. |

## Editing docker-compose.yml

Hand-maintained **source of truth** — edit it directly, image tags included. Config-file
mounts should point at `./services/<name>/…`.

> Image **versions** here are the single source of truth: the setup CLI's version engine
> (`scripts/setup/versions.py` — image pulling + the `doctor` / `update --check` drift
> report) reads them straight from the `image:` lines. `THIRD_PARTY_IMAGE_META` in
> `scripts/setup/config.py` holds only per-image resolution *metadata* (stable-track
> prefix + update constraint), not versions — so a version bump is a **one-file edit
> here**, with no second place to keep in sync (#12).
