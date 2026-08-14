# RabbitMQ Configuration - Minder Platform

**Image:** `rabbitmq:4.3.4-management` (`docker/docker-compose.yml`)
**Purpose:** Message broker, provisioned and health-checked — **not currently used by any Minder service**

---

## Overview

RabbitMQ runs as part of the `core` bundle (management UI reachable via Traefik,
`rabbitmq-diagnostics -q ping` healthcheck) but **no application code in this
repo currently publishes or consumes a message through it** — confirmed by
`grep -rl "pika\|rabbitmq" src/services/ src/shared/` returning nothing. The
exchanges/queues/producer-consumer code below (`docs/examples/rabbitmq_example.py`)
are a worked *example* of how a service could integrate, not a description of
live behavior — everything under "Exchanges", "Queues", "Policies", and
"Integration with Minder Services" is a design sketch, not shipped
infrastructure. If you're debugging why plugin tasks aren't flowing through
RabbitMQ: they never have — plugins run in-process, invoked directly by
plugin-registry/plugin-state-manager, not dispatched over a queue.

This file previously presented the exchanges/queues/policies below as if they
were live, and cited `#34` ("plugins don't exist yet") as the reason no real
definitions were loaded — that citation is now stale too: the crypto/network/
news/tefas/weather plugins have shipped and run in production for months, they
just don't use RabbitMQ.

---

## Configuration Files

### rabbitmq.conf

The actual, applied config (`docker/services/rabbitmq/rabbitmq.conf`, mounted
read-only): memory/disk limits, the management plugin's port, connection
tuning, and a `default_queue_type = quorum` default — this last one only takes
effect for a queue an application declares, which none currently do.

### definitions.json — not shipped

There is **no** bundled `definitions.json`. RabbitMQ is provisioned via env
(`RABBITMQ_DEFAULT_USER`/`PASS`) only; `rabbitmq.conf` carries no
`load_definitions` directive, and nothing declares exchanges/queues at startup
or at runtime.

The previously-tracked export was removed under #27 — it was stale (v3.13, no
`password_hash`, so loading it would clobber the default-user credential) and
referenced plugin queues (`plugin.{crypto,network,news,tefas,weather}`) that,
even today, no code publishes to or consumes from. If a real integration is
ever built, export a fresh definitions set from a running broker (see
[Export Definitions](#export-definitions) below) and wire a
`load_definitions` directive.

---

## A worked example, not live infrastructure

`docs/examples/rabbitmq_example.py` sketches what a producer/consumer
integration could look like — a `plugin.tasks` direct exchange +
per-plugin quorum queues with DLQs, and a `minder.events` topic exchange for
pub/sub. It is example code under `docs/`, not imported by any service
(`RabbitMQProducer`/`RabbitMQConsumer` have zero real callers). Read it if
you're designing an actual integration; don't assume any of its exchange/queue
names exist on a running broker — they don't until something declares them.

---

## Access

### AMQP Port
- **Port**: 5672
- **Protocol**: AMQP 0-9-1 (only matters once something actually connects)

### Management UI
- **URL**: http://localhost:15672 (or `rabbitmq.minder.local` via Traefik)
- **Username**: minder
- **Password**: `RABBITMQ_PASSWORD` from `.env`

With no application-declared topology, the Management UI will show the
built-in system exchanges and no queues — that's expected, not a sign
something is broken.

---

## Operations

### Start RabbitMQ
```bash
docker compose -f docker/docker-compose.yml up -d rabbitmq
```

### Check Status
```bash
docker ps | grep rabbitmq
curl -u minder:${RABBITMQ_PASSWORD} http://localhost:15672/api/overview
```

### View Queues
```bash
curl -u minder:${RABBITMQ_PASSWORD} http://localhost:15672/api/queues
```

---

## Security

- Strong password (`RABBITMQ_PASSWORD` in `.env`)
- Default user (`guest`) disabled — only the configured `minder` user exists
- Management UI reachable only via Traefik (+ `authelia-forwardauth` where configured)

### Password Generation
```bash
openssl rand -base64 32
```

---

## Performance Tuning (`rabbitmq.conf`)

- **Memory watermark**: 40% of RAM (`vm_memory_high_watermark.relative`)
- **Disk limit**: 50MB minimum free space (`disk_free_limit.absolute`)
- **Heartbeat**: 60 seconds
- **Channel max**: 2048
- **Connection max**: unlimited
- **Default queue type**: quorum (applies to any queue an application later declares)

---

## Backup and Restore

Only meaningful once something has actually declared exchanges/queues/policies
to export.

### Export Definitions
```bash
curl -u minder:${RABBITMQ_PASSWORD} \
  http://localhost:15672/api/definitions > rabbitmq-backup.json
```

### Import Definitions
```bash
curl -u minder:${RABBITMQ_PASSWORD} \
  -X POST \
  -H "content-type:application/json" \
  -d @rabbitmq-backup.json \
  http://localhost:15672/api/definitions
```

---

## References

- [RabbitMQ Documentation](https://www.rabbitmq.com/docs)
- [Management Plugin](https://www.rabbitmq.com/management.html)
- [Configuration Guide](https://www.rabbitmq.com/configure.html)
- [Queue Types](https://www.rabbitmq.com/queues.html)

---

**Last Updated:** 2026-08-14
**Maintained by:** Minder Platform Team
