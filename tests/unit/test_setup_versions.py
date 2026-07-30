"""Unit tests for pull_image_with_fallback retag behaviour (scripts/setup/versions.py).

#178: `update` pulled the smart-resolved newer image but ran the pinned version,
because the resolved ref was never retagged to the compose-pinned ref that the
rolling `compose up` references. Lock in the retag: pull resolved → tag it to the
pin, but only when they differ (the SKIP_VERSION_CHECK path resolves to the pin
and must stay a plain pull — that's what the parity gate compares).

No Docker: docker.run is a recording stub.
"""

import pytest

from scripts.setup import versions


@pytest.fixture
def rec_run(monkeypatch):
    """Record docker.run(*cmd) calls; every call succeeds (rc 0)."""
    calls: list[tuple] = []
    monkeypatch.setattr(
        versions.docker, "run", lambda *cmd, **k: calls.append(cmd) or 0
    )
    return calls


def test_retag_when_resolved_differs_from_pin(monkeypatch, rec_run):
    monkeypatch.setattr(versions, "resolve_image_tag", lambda spec: "traefik:v3.7.9")
    versions.pull_image_with_fallback("traefik:v3.7.8|v3|none")
    assert ("docker", "pull", "traefik:v3.7.9") in rec_run
    # the fix: pinned ref now points at the freshly-pulled newer image
    assert ("docker", "tag", "traefik:v3.7.9", "traefik:v3.7.8") in rec_run


def test_no_retag_when_resolved_equals_pin(monkeypatch, rec_run):
    """SKIP_VERSION_CHECK / patch-constraint path: resolve returns the pin → plain
    pull, no tag (keeps parity with the gate's dry+skip trace)."""
    monkeypatch.setattr(
        versions, "resolve_image_tag", lambda spec: "redis:8.8.0-alpine"
    )
    versions.pull_image_with_fallback("redis:8.8.0-alpine|8|none")
    assert ("docker", "pull", "redis:8.8.0-alpine") in rec_run
    assert not any(c[:2] == ("docker", "tag") for c in rec_run)


def test_pull_failure_falls_back_to_pin_no_retag(monkeypatch):
    """Resolved pull fails → fall back to pulling the pin; no retag (we're already
    on the pin)."""
    monkeypatch.setattr(versions, "resolve_image_tag", lambda spec: "traefik:v3.7.9")
    calls: list[tuple] = []

    def run(*cmd, **k):
        calls.append(cmd)
        # first pull (resolved) fails; everything else succeeds
        if cmd == ("docker", "pull", "traefik:v3.7.9"):
            return 1
        return 0

    monkeypatch.setattr(versions.docker, "run", run)
    rc = versions.pull_image_with_fallback("traefik:v3.7.8|v3|none")
    assert rc == 0  # non-fatal
    assert ("docker", "pull", "traefik:v3.7.8") in calls  # pinned fallback
    assert not any(c[:2] == ("docker", "tag") for c in calls)
