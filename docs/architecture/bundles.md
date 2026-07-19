# ADR: Bundle Model — Capability-Oriented Service Control-Plane

> **Status:** Accepted — Phases 0-2 shipped (#62), first Phase-3 slice shipped (#64);
> remaining Phase 3 tracked in #65 · **Date:** 2026-07-18 · **Supersedes:** the ad-hoc
> `plugin enable/disable` control-plane (branch `feat/plugin-lifecycle-gating`, renamed
> to the bundle model in Phase 1 and merged as `feat/bundles`).

## Context

Minder is a modular platform: users should be able to turn capabilities (monitoring,
RAG, chat, …) on and off, each capability being a group of services. The existing
`setup.sh plugin enable/disable` slice hard-coded an `owned`/`shared` split and a
`CORE_CONSUMERS` list. Two problems drove a redesign:

1. **"plugin" was overloaded** — it already means a code handler (`plugin-registry`,
   `src/plugins/`, `PluginMetadata`, `/v1/plugins`). Reusing it for "a group of
   services" would confuse contributors.
2. **`owned`/`shared` is not a static property.** As the marketplace lets users
   install new plugins over time, a service that one bundle owns today can become
   shared tomorrow. Ownership must be *derived*, never stored.

This ADR fixes the vocabulary, the model, the service→bundle map, binding
resolution, the repo layout, and the phased plan.

## Vocabulary

| Term | Meaning |
|------|---------|
| **service** | a single container (a Compose service) |
| **bundle** | a named group of services delivering a capability; the enable/disable + refcount unit |
| **core** | the always-on bundle (the kernel); cannot be disabled |
| **plugin** | a first-party code handler (`src/plugins/`) that manages and/or introduces a bundle. A plugin may own **no** services (pure integration — e.g. `network`) |
| **manager** | (role) a small housekeeping service that configures/manages a bundle's service(s) — e.g. `telegraf` for monitoring, `model-management` for inference. One instance; not on the request path |
| **claim** | a bundle's declared need for a service |
| **referenced** | (derived) a service claimed by ≥1 *enabled* bundle → keep it up |
| **orphan** | (derived) a service claimed by 0 enabled bundles → GC candidate |
| **reconcile** | converge the running services to the enabled bundles |

Naming rationale (chosen over rivals): `bundle` (OSGi — dynamically installed,
dependency-declaring, shareable module) over `feature`/`stack`/`module`/`profile`
(collide with product-flags / "the whole stack" / `module plugin` / Docker
`COMPOSE_PROFILES`+`COMPUTE_RESOURCE_PROFILE`). `claim` (k8s PersistentVolumeClaim),
`orphan`/`reconcile` (k8s GC / controllers), `service`/`core` (Compose / existing
"Minder Core API"). This is a best-of-breed synthesis; no single system names all
of these concepts.

## Model — reference-counted garbage collection

The one operational rule:

> A **service is up iff ≥1 enabled bundle claims it.** A service claimed by 0 enabled
> bundles is an **orphan** (GC candidate). `owned` (exactly 1 claimant) and `shared`
> (≥2) are **derived, display-only** states — never stored in config.

This is the model of Nix/Guix store GC, Kubernetes owner-references + GC, and
systemd `Wants`/`Requires`. The `_consumers`/`_orphans_after` "brain" already
computes claimants live; the fix is conceptual (store only claims, derive the rest)
and terminological.

Reuse of already-running services is automatic: `docker compose up -d <svc>` on a
running service is a no-op, so bundles sharing a service never duplicate or restart
it; refcount governs teardown. (Verified live: enabling telegraf showed influxdb
`Running`, i.e. reused, not `Started`.)

### The claim graph is dynamic

The claim graph has three sources, merged into one `service → claimants` map:

1. **Platform bundles** — declared via a Compose label on each service (below).
2. **Plugin-contributed bundles** — a plugin declares its claims in its manifest;
   installing the plugin adds its claims to the graph.
3. **Marketplace** — installs new plugins (hence new bundles/claims) at runtime.

## Bundle map (all 32 services assigned)

| Bundle | Services | Default |
|--------|----------|---------|
| **core** (always-on) | traefik, postgres, redis, rabbitmq, api-gateway, plugin-registry, plugin-state-manager, marketplace, neo4j, minio, schema-registry | ON (mandatory) |
| **monitoring** | influxdb, telegraf, prometheus, grafana, alertmanager, jaeger, otel-collector, postgres-exporter, redis-exporter, rabbitmq-exporter, node-exporter, cadvisor, blackbox-exporter | **OFF** |
| **inference** | ollama, model-management | ON |
| **rag** | rag-pipeline, qdrant, ollama | ON |
| **graph-rag** | graph-rag | **OFF** |
| **chat** | openwebui, rag-pipeline, ollama | ON |
| **voice** | tts-stt | **OFF** |

> The `core` map above is `bundles.BUNDLES["core"]["claims"]` as shipped. **authelia**
> is NOT in the claim map yet (it's disabled — issue #15); the design intent is for it
> to join `core` when #15 re-enables it. `rag`/`chat` share `ollama` (and `chat` shares
> `rag-pipeline`) so the refcount can't orphan a service another enabled bundle needs.

Notes:
- **marketplace is core** → neo4j is always on (marketplace uses it for the
  dependency graph; graph-rag is a second claimant when enabled). neo4j is *not*
  a RAG dependency (RAG uses qdrant).
- **monitoring observes core but core never depends on monitoring** (exporters /
  prometheus / telegraf read core services one-directionally) → monitoring is safe
  to disable; core keeps running, just unobserved.
- **chat → rag coupling:** `openwebui` declares `depends_on: rag-pipeline`, so
  enabling chat claims rag-pipeline anyway — hence chat and rag default together.

## Binding — how a claimed service is provided

A claim resolves to a **binding**, per deployment:

| Binding | Provider | Refcount / GC |
|---------|----------|----------------|
| **managed** | a container the platform/bundle runs (or a plugin self-hosts) | yes — enters the graph |
| **external** | a configured address on the network (e.g. `OLLAMA_BASE_URL=http://gpu:11434`, external Postgres) | no — nothing to GC; reachability-probed only |

This generalises the proven `OLLAMA_BASE_URL` local/remote pattern to every service.

> **Implemented so far (2026-07-19):** the control-plane already honours the ONE
> binding that exists today — `ollama` via `OLLAMA_BASE_URL` (`bundles.EXTERNAL_BINDINGS`).
> When it is set, `bundle status` shows ollama as `⇄ external → <url>` (not orphan-drift)
> and `enable`/`reconcile` never start the internal container. The general resolution
> matrix below (self-host / prompt) is still Phase 3.

Resolution matrix (per claim):

| Address configured? | Plugin can self-host? | Result |
|---|---|---|
| yes | (either) | **external** — connect, don't manage |
| no | yes | **managed** — bring it up (self-host) |
| no | no | **error/prompt** — "no address and I can't self-host X; give me one" |

Default when no address is given: **prompt** the user (interactive); in
`NONINTERACTIVE`/CI an explicit config/flag is required or resolution errors.
A managed self-hosted service enters the refcount graph like any other (it can
become shared). Self-hosting plugins ship a service spec (see Repo Structure); the
trust boundary is therefore the **service spec** (image/mounts/privileges), not the
handler code (review/signing deferred — see Open Items).

### Provider chain (primary/fallback) — compatible future

A claim's binding may be an ordered **provider chain** `[primary, fallback…]`, each
provider external or managed. Two layers:

- **Resolution-time** (static: pick primary if configured, else managed) — Phase 1–2.
- **Runtime failover** (primary health-fails → route to standby → return when it
  recovers) + **capacity-aware weighted routing** across a **provider pool**
  (capacity derived from Ollama's own `eval_count`/`eval_duration` → tokens/sec) —
  this is **Layer 2**, tracked as epic **#21 (multi-ollama work-based routing)**,
  built later. The chain modelled now extends to a pool then with no rewrite.

## Two layers

```
Layer 1 — LIFECYCLE (this ADR): which services exist (managed/external), up/down,
          refcount/GC, bundle enable/disable/reconcile.
Layer 2 — ROUTING (#21): given the live provider pool, distribute inference
          requests by measured capacity, failover, rebalance. Separate epic.
```

## Manager lifecycle

There is **one** instance of each manager (e.g. `model-management`, `telegraf`). A
manager runs iff its bundle is **active** (≥1 of the bundle's services is live). It
is a housekeeper (configure/manage), **not** on any consumer's request path, and it
never brings up its bundle's backing service — the *binding* does that (reusing an
existing/external one; self-hosting only when none exists).

## Default enablement & install profiles

Fresh-install default = the **standard** profile: `core + inference + chat + rag`
("install → talk to a local LLM, optionally over your docs"). Heavy/ops
(`monitoring`) and specialised (`graph-rag`, `voice`) are opt-in.

```
setup.sh install                    # standard (default)
setup.sh install --profile minimal  # core only
setup.sh install --profile full     # everything
```

A profile only **seeds** `bundles.state.json` at install — it is not a persistent
mode and there is no lock-in. Post-install, bundles are toggled freely (`bundle
enable/disable`). A post-install `bundle profile <name>` re-apply (with `--exact` to
also disable extras) is **planned, not yet implemented** — `install --profile` is the
only profile entry point today.

## Control surface

Same operations, two front-ends over one shared brain:

- **Host CLI (Phases 1–2, shipped):**
  `setup.sh bundle enable|disable|status|reconcile <name> [--stop-orphans]` and
  `setup.sh install --profile <name>`. (`setup.sh bundle profile <name>` for a
  post-install re-apply is planned — not yet implemented.)
- **Registry API (Phase 3):** `GET /v1/bundles`, `POST /v1/bundles/{name}/enable|disable`,
  `POST /v1/bundles/reconcile`, `POST /v1/bundles/profile/{name}`. The
  container-orchestration privilege runs through a **docker-socket-proxy**
  (whitelist start/stop/restart) behind **Authelia**. This also enables
  marketplace-triggered auto-enable of a bundle on plugin install.

`disable` never deletes data (`stop`, not `down`; volumes persist). There is **no
per-bundle purge**; the only purge is the existing platform-wide `uninstall
--purge`.

`start`/`restart` **converge to the desired state** (GitOps-style): they bring up
every enabled bundle's services and **stop** any service no enabled bundle claims
(a bundle disabled while running is brought down on the next start/restart). The
immediate `disable` is notify-only by default (non-disruptive); the persisted
intent is enforced on the next converge.

## Repo structure

Principles: single source of truth · plugin self-containment · runtime state clearly
separated from tracked config.

- **Bundle membership derived from Compose labels** (no parallel file):
  ```yaml
  grafana:
    labels: [minder.bundle=monitoring]
  ```
- **Plugins are self-contained:**
  ```
  src/plugins/<name>/
    __init__.py     # handler
    manifest.yml    # bundle, claims[] (self_hostable/address_env/spec-ref), manager?, providers?
    service.yml     # (optional) Compose fragment for a self-hostable managed service
    README.md
  ```
- **New plugin-contributed services merge at runtime** via `docker compose -f
  base.yml -f <plugin>/service.yml … up`. The base stays **hand-maintained** (no
  generation — respects the #31 decision; fragments are additive overlays at `up`
  time, the base is never regenerated).
- **Activation = explicit service list** computed from the claim graph
  (`compose -f … up -d <services>`); Compose profiles are not needed for bundles
  (the `internal-ollama` profile stays for ollama binding only).
- **All runtime state under one gitignored, self-healing hidden dir:**
  ```
  .minder/          # gitignored (like the existing .cache/)
    bundles.state.json
    telegraf.runtime.conf
    compose.env      # mirror of root .env
  ```
  Recreated by `setup.sh start` (prepare) if deleted — same self-heal as `.env`.
  (Move is a dedicated small step, since it touches mount paths.)
- **Control-plane:** `scripts/setup/bundles.py` (verb + brain). In Phase 3 the pure
  brain moves to `shared/` so the host CLI and the registry API import the same
  logic (giving the ~unused `shared/` a real purpose).

## Decisions

| # | Decision |
|---|----------|
| Vocabulary | `service · bundle · core · plugin · manager · claim · referenced/orphan · reconcile` |
| owned/shared | derived display states, never stored; operational binary is referenced-vs-orphan |
| marketplace | **core** (→ neo4j always on) |
| inference | optional **bundle**; `model-management` is its manager; ollama via binding |
| authelia | **core** (security), when enabled (#15) |
| minio · schema-registry | **core** |
| jaeger · otel-collector | **monitoring** |
| default | standard profile = `core+inference+chat+rag`; profiles minimal/standard/full; no lock-in |
| binding | managed / external / self-host; no-address → prompt (CI → explicit); provider-chain now, pool/#21 later |
| new containers | allowed via plugin-shipped service spec; review/signing **deferred** |
| secrets | external-binding creds in `.env` (state stays secret-free); better store = future work |
| disable | `stop` (data kept); **no per-bundle purge** |
| membership | derived from Compose labels; new services via `compose -f` merge (no generation) |
| runtime state | single gitignored self-healing `.minder/` |

## Open items (non-blocking; tracked)

- **Security debt (internet-exposed Pi):** (a) marketplace plugins may introduce new
  containers with **no review/signing yet** — add a trust layer (signed/reviewed
  service specs) before opening a public marketplace; (b) the registry already holds
  `docker.sock:rw` (compose line ~507) — narrow it behind a **docker-socket-proxy**
  (Phase 3). Authelia gates the API perimeter but does **not** contain a compromised
  registry process — it is not a substitute for least privilege.
- **Conflict/version resolution** (two bundles want a shared service at different
  versions/config) → owned by the marketplace dependency+conflict graph.
- **External-binding health** in `bundle status` (reachability probe) — Phase 4.
- **Manager relevance with a fully-external service** (does `model-management` run if
  ollama is external-only?) — refinement, Phase 2+.
- **Control-plane audit log** (who/when enabled/disabled) — nice-to-have.

## Phased plan

| Phase | Work |
|-------|------|
| **0** | This ADR (design lock) |
| **1** | Rename `plugin`→`bundle` (verb, `bundles.state.json`, `BUNDLES` claim-graph, no owned/shared fields); binding managed/external; keep gate/tests green |
| **2** | Real bundle map (Compose labels) + profiles + `start`→reconcile wiring; provider-chain (resolution-time) |
| **3** | docker-socket-proxy + registry API → shared brain; plugin manifest schema; marketplace bundle contribution |
| **4** | Binding polish (external health), `.minder/` state consolidation, Layer-2/#21 groundwork |

> Layer 2 (#21 capacity-aware inference routing) is a separate epic; the
> provider-chain here is forward-compatible with the provider pool it needs.
