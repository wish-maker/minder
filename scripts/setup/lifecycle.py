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

from . import config, docker, env, log


def start_services() -> None:
    log.step("Starting all services")

    # Ollama mode: an exported OLLAMA_BASE_URL wins (CLI override), else read .env.
    # Non-empty → external mode: deactivate the 'internal-ollama' profile so the
    # platform ollama container never starts. Empty → internal mode: activate it.
    ollama_url = os.environ.get("OLLAMA_BASE_URL") or env.get("OLLAMA_BASE_URL")
    if ollama_url:
        log.info("🌐 External Ollama mode (OLLAMA_BASE_URL set)")
        log.info(f"   OLLAMA_BASE_URL: {ollama_url}")
        log.info(
            "   Platform-managed ollama container will NOT start (compose 'internal-ollama' profile inactive)"
        )
        os.environ.pop("COMPOSE_PROFILES", None)
    else:
        log.info(
            "🏠 Internal Ollama mode (platform-managed container, default zero-config)"
        )
        log.info("   OLLAMA_BASE_URL: (empty, using internal minder-ollama container)")
        os.environ["COMPOSE_PROFILES"] = "internal-ollama"

    log.info("① Security layer…")
    docker.compose("up", "-d", *config.SECURITY_SERVICES)
    time.sleep(5)

    log.info("② Infrastructure (DB, cache, vector store, AI runtime)…")
    docker.compose("up", "-d", *config.CORE_SERVICES)
    time.sleep(8)

    log.info("③ Message broker (RabbitMQ)…")
    # RabbitMQ is already in CORE_SERVICES; just wait for it to be healthy.
    docker.wait_healthy("rabbitmq", config.TIMEOUT_SERVICES)

    log.info("④ Core microservices…")
    docker.compose("up", "-d", *config.API_SERVICES)
    time.sleep(5)

    log.info("⑤ Monitoring stack…")
    docker.compose("up", "-d", "influxdb", "telegraf")
    docker.compose_monitoring("up", "-d", "prometheus", "grafana", "alertmanager")
    docker.compose("up", "-d", *config.MONITORING_SERVICES)
    time.sleep(5)

    log.info("⑥ AI enhancement services…")
    docker.compose("up", "-d", *config.AI_SERVICES)
    time.sleep(5)

    log.info("⑦ Metrics exporters…")
    docker.compose_monitoring("up", "-d", *config.EXPORTER_SERVICES)

    log.success("All service groups dispatched")


def wait_for_services() -> None:
    """bash wait_for_services: wait each service group healthy (best-effort; the
    bash `|| true` per svc is mirrored by ignoring wait_healthy's return)."""
    log.section("⏳  Waiting for Services")
    for svc in config.CORE_SERVICES:
        docker.wait_healthy(svc, config.TIMEOUT_SERVICES)
    for svc in config.API_SERVICES:
        docker.wait_healthy(svc, config.TIMEOUT_SERVICES)
    for svc in config.MONITORING_SERVICES:
        docker.wait_healthy(svc, config.TIMEOUT_MONITORING)
    for svc in config.AI_SERVICES:
        docker.wait_healthy(svc, config.TIMEOUT_AI)
