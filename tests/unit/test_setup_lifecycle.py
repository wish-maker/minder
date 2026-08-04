"""Unit tests for the created-but-not-started reconciliation (#197, #292).

`wait_for_services` recovers services compose left in the 'created' state (a
`depends_on: service_healthy` dependency that didn't go healthy in time under
load). Guards: only ENABLED created services are started, DRY_RUN is a no-op, an
empty set does nothing, and `docker.created_services()` strips the prefix +
ignores foreign containers.

#292: the original single reconcile call (between the CORE and API_SERVICES
wait loops) only recovers API-tier staleness caused by a slow CORE-tier
dependency — it cannot recover staleness caused by a slow API-tier SIBLING
(e.g. marketplace/plugin-state-manager stuck behind a slow plugin-registry,
all in the same API_SERVICES group), since that race can still be live at the
one call site. A second reconcile pass at the end of `wait_for_services`,
after every tier's full wait timeout, catches those.

No Docker: docker.created_services / docker.compose / docker.wait_healthy /
bundles.service_active and docker.capture are stubbed.
"""

import pytest

from scripts.setup import config, docker, lifecycle


@pytest.fixture
def rec_compose(monkeypatch):
    """Record docker.compose(...) calls; return rc 0."""
    calls: list[tuple] = []
    monkeypatch.setattr(docker, "compose", lambda *a: calls.append(a) or 0)
    monkeypatch.setattr(config, "DRY_RUN", False)
    return calls


def test_created_enabled_services_are_started(monkeypatch, rec_compose):
    monkeypatch.setattr(docker, "created_services", lambda: ["graph-rag"])
    monkeypatch.setattr(lifecycle.bundles, "service_active", lambda s: True)
    lifecycle._reconcile_created()
    assert rec_compose == [("up", "-d", "graph-rag")]


def test_disabled_bundle_service_is_skipped(monkeypatch, rec_compose):
    # graph-rag is 'created' but its bundle is disabled → leave it for orphan-convergence
    monkeypatch.setattr(docker, "created_services", lambda: ["graph-rag"])
    monkeypatch.setattr(lifecycle.bundles, "service_active", lambda s: False)
    lifecycle._reconcile_created()
    assert rec_compose == []


def test_nothing_created_is_noop(monkeypatch, rec_compose):
    monkeypatch.setattr(docker, "created_services", lambda: [])
    monkeypatch.setattr(lifecycle.bundles, "service_active", lambda s: True)
    lifecycle._reconcile_created()
    assert rec_compose == []


def test_dry_run_is_noop(monkeypatch, rec_compose):
    # Must not even query docker under DRY_RUN.
    monkeypatch.setattr(config, "DRY_RUN", True)

    def _boom():
        raise AssertionError("created_services must not be queried under DRY_RUN")

    monkeypatch.setattr(docker, "created_services", _boom)
    lifecycle._reconcile_created()
    assert rec_compose == []


def test_created_services_parses_and_filters(monkeypatch):
    # prefix stripped; a foreign (non-minder) container is ignored.
    monkeypatch.setattr(config, "CONTAINER_PREFIX", "minder")
    monkeypatch.setattr(
        docker,
        "capture",
        lambda argv: "minder-graph-rag\nminder-neo4j\nsome-other-container\n",
    )
    assert docker.created_services() == ["graph-rag", "neo4j"]


def test_wait_for_services_reconciles_twice(monkeypatch):
    """#292: a service stuck behind a still-racing API-tier sibling at the
    first reconcile call must get a second chance after all tiers finish
    waiting — not be left 'Created' forever."""
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(lifecycle, "_active", lambda services: list(services))
    monkeypatch.setattr(docker, "wait_healthy", lambda *a, **k: True)
    monkeypatch.setattr(lifecycle.bundles, "service_active", lambda s: True)

    # First reconcile call (mid-function) still sees the stuck service (its
    # blocking sibling hasn't become healthy yet); by the second call
    # (end-of-function) it has recovered.
    calls = {"n": 0}

    def created_services():
        calls["n"] += 1
        return ["marketplace"] if calls["n"] == 1 else []

    monkeypatch.setattr(docker, "created_services", created_services)
    compose_calls: list[tuple] = []
    monkeypatch.setattr(docker, "compose", lambda *a: compose_calls.append(a) or 0)

    lifecycle.wait_for_services()

    assert calls["n"] == 2  # reconcile queried created_services twice
    assert compose_calls == [("up", "-d", "marketplace")]
