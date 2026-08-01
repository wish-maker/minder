"""Unit tests for the `status` Ollama-backend line (#21 observability).

In failover mode the status view probes the primary so a primary outage reads as
"on the internal fallback" instead of unexplained slowness. Guards the mode → line
mapping (bash cmd_status mirrors this text for the parity gate).
"""

from scripts.setup import status


def _run(monkeypatch, primary, base, reachable=True):
    emitted = []
    monkeypatch.setattr(status.log, "_emit", lambda s="": emitted.append(s))
    vals = {"OLLAMA_FAILOVER_PRIMARY": primary, "OLLAMA_BASE_URL": base}
    monkeypatch.setattr(status.env, "get", lambda k: vals.get(k, ""))
    monkeypatch.setattr(status, "_primary_reachable", lambda hp: reachable)
    status._print_ollama_backend()
    return "\n".join(emitted)


def test_failover_primary_reachable(monkeypatch):
    out = _run(monkeypatch, "192.168.68.104:11434", "http://minder-ollama-router:11434")
    assert "REACHABLE" in out and "external primary" in out
    assert "192.168.68.104:11434" in out


def test_failover_primary_unreachable(monkeypatch):
    out = _run(
        monkeypatch,
        "10.0.0.9:11434",
        "http://minder-ollama-router:11434",
        reachable=False,
    )
    assert "UNREACHABLE" in out and "internal fallback" in out


def test_external_mode(monkeypatch):
    out = _run(monkeypatch, "", "http://gpu-node:11434")
    assert "external — http://gpu-node:11434" in out
    assert "REACHABLE" not in out  # no probe in external mode


def test_internal_mode(monkeypatch):
    out = _run(monkeypatch, "", "")
    assert "internal — platform-managed container" in out


def test_primary_reachable_false_when_router_absent(monkeypatch):
    # Probes via `docker exec <router> wget …`. When the router container is absent
    # (or docker missing) the probe must return False gracefully — never raise.
    class _Res:
        returncode = 1

    monkeypatch.setattr(status.subprocess, "run", lambda *a, **k: _Res())
    assert status._primary_reachable("127.0.0.1:1") is False

    def _boom(*a, **k):
        raise OSError("docker not found")

    monkeypatch.setattr(status.subprocess, "run", _boom)
    assert status._primary_reachable("10.0.0.9:11434") is False
