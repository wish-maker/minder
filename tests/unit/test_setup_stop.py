"""Unit tests for stop.run()'s down-status reporting (#348).

#348: `docker.compose_all("down")`'s return value used to be discarded while
"All services stopped" fired unconditionally — a container refusing to stop
was reported identically to a clean shutdown. No Docker: docker.* is stubbed.
"""

from scripts.setup import stop


def _quiet(monkeypatch):
    monkeypatch.setattr(stop.log, "step", lambda *a, **k: None)
    monkeypatch.setattr(stop.docker, "network_exists", lambda name: False)
    monkeypatch.setattr(stop.config, "CLEAN_DANGLING", False)


def test_reports_success_when_compose_down_succeeds(monkeypatch):
    _quiet(monkeypatch)
    monkeypatch.setattr(stop.docker, "compose_all", lambda *a, **k: 0)
    succeeded = []
    monkeypatch.setattr(stop.log, "success", lambda m: succeeded.append(m))

    rc = stop.run()

    assert rc == 0
    assert any("All services stopped" in m for m in succeeded)


def test_warns_instead_of_false_success_when_compose_down_fails(monkeypatch):
    _quiet(monkeypatch)
    monkeypatch.setattr(stop.docker, "compose_all", lambda *a, **k: 1)
    succeeded = []
    monkeypatch.setattr(stop.log, "success", lambda m: succeeded.append(m))
    warned = []
    monkeypatch.setattr(stop.log, "warn", lambda m: warned.append(m))

    rc = stop.run()

    assert rc != 0
    assert not any("All services stopped" in m for m in succeeded)
    assert warned
