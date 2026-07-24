# docker/services/ — per-service configuration files

This directory holds the **static configuration files** that are bind-mounted into
the platform's third-party service containers. It is **not** the deployment entry
point — the compose files live in [`../compose/`](../compose/), and orchestration is
driven by `setup.sh` / `docker compose --file docker/compose/docker-compose.yml ...`.

Each subdirectory is the source of truth for one service's config (mounted read-only
into the container by `docker/compose/docker-compose.yml`):

| Dir | Mounted into | Contents |
|-----|--------------|----------|
| `postgres/`        | postgres        | `init.sql` (DB + aux-DB bootstrap) |
| `prometheus/`      | prometheus      | scrape config, alert rules, blackbox targets |
| `alertmanager/`    | alertmanager    | alert routing |
| `grafana/`         | grafana         | provisioned dashboards + datasources |
| `telegraf/`        | telegraf        | `telegraf.conf` (+ runtime managed region) |
| `traefik/`         | traefik         | `traefik.yml` + `dynamic/` (routers, middleware, access-mode) |
| `otel-collector/`  | otel-collector  | collector pipeline config |
| `rabbitmq/`        | rabbitmq        | `rabbitmq.conf` |
| `ollama/`          | ollama          | `init-models.sh` |
| `authelia/`        | authelia        | config + users DB (**service currently disabled**) |

> **Editing config here changes runtime behavior on the next `restart`/`up`.** For
> the service map, ports, and operational commands see the root
> [`README.md`](../../README.md), [`docs/architecture/`](../../docs/architecture/),
> and the CLAUDE.md service map. This is a development environment — production
> hardening is not yet applied.
