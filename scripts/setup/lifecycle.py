"""Service lifecycle — ported from scripts/lib/lifecycle.sh (#7, Stage 2).

`start_services` brings the stack up in ordered groups via dry-run-gated
`compose up`, gating the platform-managed ollama container on the compose
'internal-ollama' profile (active only when OLLAMA_BASE_URL is empty). The
compose calls go through docker.compose()/compose_monitoring() (dry-run-gated),
so start_services is non-destructive under DRY_RUN — which is how it is verified.

wait_for_services waits each group healthy (a thin loop over the ported
wait_healthy). Live it would block to the timeouts on no-healthcheck services;
it is verified under the gate's docker shim (container_health → healthy → instant).
"""

import os
import time

from . import bundles, config, docker, env, log


def _active(services: "tuple[str, ...]") -> "list[str]":
    """Keep only services whose claiming bundle is enabled (bundles.service_active).
    With everything enabled (the default + the setup gate) the list is unchanged, so
    each group's `compose up` stays byte-identical to the frozen bash reference."""
    return [s for s in services if bundles.service_active(s)]


def start_services() -> None:
    log.step("Starting all services")

    # Ollama mode: an exported value wins (CLI override), else read .env.
    #  - OLLAMA_FAILOVER_PRIMARY set → failover: run BOTH the router (external primary)
    #    and the internal container (backup); consumers point at the router.
    #  - else OLLAMA_BASE_URL set → external: internal-ollama profile inactive.
    #  - else                     → internal: activate the internal-ollama profile.
    ollama_url = os.environ.get("OLLAMA_BASE_URL") or env.get("OLLAMA_BASE_URL")
    failover_primary = os.environ.get("OLLAMA_FAILOVER_PRIMARY") or env.get(
        "OLLAMA_FAILOVER_PRIMARY"
    )
    failover_mode = bool(failover_primary)
    if failover_mode:
        log.info("🔀 Failover Ollama mode (external primary + internal fallback)")
        log.info(f"   Primary: {failover_primary}  →  backup: internal minder-ollama")
        log.info("   Consumers reach ollama via the minder-ollama-router")
        os.environ["COMPOSE_PROFILES"] = "internal-ollama,ollama-router"
    elif ollama_url:
        log.info("🌐 External Ollama mode (OLLAMA_BASE_URL set)")
        log.info(f"   OLLAMA_BASE_URL: {ollama_url}")
        log.info(
            "   Platform-managed ollama container will NOT start (compose 'internal-ollama' profile inactive)"
        )
        os.environ.pop("COMPOSE_PROFILES", None)
    elif bundles.service_active("ollama"):
        # ollama is claimed by inference/rag/chat — start it if any of them is on.
        log.info(
            "🏠 Internal Ollama mode (platform-managed container, default zero-config)"
        )
        log.info("   OLLAMA_BASE_URL: (empty, using internal minder-ollama container)")
        os.environ["COMPOSE_PROFILES"] = "internal-ollama"
    else:
        log.info("⏸️  no bundle claims ollama — internal ollama will NOT start")
        os.environ.pop("COMPOSE_PROFILES", None)

    log.info("① Security layer…")
    docker.compose("up", "-d", *config.SECURITY_SERVICES)
    time.sleep(5)

    log.info("② Infrastructure (DB, cache, vector store, AI runtime)…")
    docker.compose("up", "-d", *_active(config.CORE_SERVICES))
    time.sleep(8)

    # The failover router has no depends_on pulling it in (consumers only hold its URL
    # as a string), so bring it up explicitly once the network exists. The internal
    # backup (minder-ollama) is pulled in by the consumers' depends_on. (#21)
    if failover_mode:
        log.info("   ↳ ollama-router (external primary + internal fallback)…")
        docker.compose("up", "-d", "ollama-router")

    log.info("③ Message broker (RabbitMQ)…")
    # RabbitMQ is already in CORE_SERVICES; just wait for it to be healthy.
    docker.wait_healthy("rabbitmq", config.TIMEOUT_SERVICES)

    log.info("④ Core microservices…")
    docker.compose("up", "-d", *_active(config.API_SERVICES))
    time.sleep(5)

    log.info("⑤ Monitoring stack…")
    # The whole observability stack is the `monitoring` bundle (influxdb/telegraf/
    # prometheus/grafana/alertmanager/jaeger/otel + exporters in ⑦). Gated on its
    # enable-state; default enabled → identical to the historical commands, keeping
    # the setup gate byte-identical. See scripts/setup/bundles.py + bundles.md.
    if bundles.is_enabled("monitoring"):
        docker.compose("up", "-d", "influxdb", "telegraf")
        docker.compose_monitoring("up", "-d", "prometheus", "grafana", "alertmanager")
        docker.compose("up", "-d", *config.MONITORING_SERVICES)
    else:
        log.detail("monitoring bundle disabled (bundles.state.json) — skipped")
    time.sleep(5)

    log.info("⑥ AI enhancement services…")
    ai_services = _active(config.AI_SERVICES)
    if ai_services:
        docker.compose("up", "-d", *ai_services)
    else:
        log.detail("no AI-enhancement bundles enabled (chat/voice) — skipped")
    time.sleep(5)

    log.info("⑦ Metrics exporters…")
    if bundles.is_enabled("monitoring"):
        docker.compose_monitoring("up", "-d", *config.EXPORTER_SERVICES)
    else:
        log.detail("monitoring bundle disabled — exporters skipped")

    # ⑧ Converge to desired state: stop any service no enabled bundle claims (a
    # bundle disabled while its services were running is brought down on start/
    # restart). Emits nothing when all bundles are enabled → the setup gate stays
    # byte-identical; only runs when something is actually disabled + orphaned.
    orphans = bundles.orphaned_services()
    if orphans:
        log.info("⑧ Converging bundles (stopping disabled services)…")
        docker.compose("stop", *orphans)

    log.success("All service groups dispatched")


def _reconcile_created() -> None:
    """Recover services compose created but never started (state 'created') because a
    `depends_on: service_healthy` dependency didn't go healthy in time under load
    (#197: a heavy `install --profile full` left graph-rag 'Created' behind a slow
    neo4j, then silently reported success). Called once the CORE deps are healthy, so
    a plain `compose up -d <svc>` now succeeds. Only touches ENABLED services; a
    disabled-bundle leftover is left for orphan-convergence. Skipped under DRY_RUN
    (there's no real stack to reconcile)."""
    if config.DRY_RUN:
        return
    created = [s for s in docker.created_services() if bundles.service_active(s)]
    if not created:
        return
    log.warn(
        f"Recovering {len(created)} service(s) created but not started "
        f"(dependency wasn't ready in time): {', '.join(created)}"
    )
    for svc in created:
        docker.compose("up", "-d", svc)


def wait_for_services() -> None:
    """bash wait_for_services: wait each service group healthy (best-effort; the
    bash `|| true` per svc is mirrored by ignoring wait_healthy's return)."""
    log.section("⏳  Waiting for Services")
    # Only wait on services whose bundle is enabled — a disabled bundle's services
    # were never started (see _active). Everything enabled → same lists as before.
    for svc in _active(config.CORE_SERVICES):
        docker.wait_healthy(svc, config.TIMEOUT_SERVICES)
    # CORE deps (e.g. neo4j) are healthy now → start anything compose left 'Created'
    # BEFORE we wait on it, so it ends up healthy instead of burning a wait timeout
    # and being reported down (#197).
    _reconcile_created()
    for svc in _active(config.API_SERVICES):
        docker.wait_healthy(svc, config.TIMEOUT_SERVICES)
    for svc in _active(config.MONITORING_SERVICES):
        docker.wait_healthy(svc, config.TIMEOUT_MONITORING)
    for svc in _active(config.AI_SERVICES):
        docker.wait_healthy(svc, config.TIMEOUT_AI)
