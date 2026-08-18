"""Unit tests for scripts/setup/stop.py's network-removal and --clean-dangling
prune branches -- the #348 down-status regression is already covered in
test_setup_stop.py. No real Docker: docker.*/subprocess.run are all stubbed.
"""

from scripts.setup import stop


def _quiet(monkeypatch):
    monkeypatch.setattr(stop.log, "step", lambda *a, **k: None)
    monkeypatch.setattr(stop.docker, "compose_all", lambda *a, **k: 0)
    monkeypatch.setattr(stop.config, "CLEAN_DANGLING", False)


class _FakeCompleted:
    def __init__(self, stdout=""):
        self.stdout = stdout


def test_removes_network_when_present(monkeypatch):
    _quiet(monkeypatch)
    monkeypatch.setattr(stop.docker, "network_exists", lambda name: True)
    calls = []
    monkeypatch.setattr(stop.docker, "run", lambda *args: calls.append(args) or 0)
    success = []
    monkeypatch.setattr(stop.log, "success", lambda m: success.append(m))

    stop.run()

    assert ("docker", "network", "rm", stop.config.NETWORK_NAME) in calls
    assert any("removed" in m for m in success)


def test_warns_when_network_removal_fails(monkeypatch):
    _quiet(monkeypatch)
    monkeypatch.setattr(stop.docker, "network_exists", lambda name: True)
    monkeypatch.setattr(stop.docker, "run", lambda *args: 1)
    warned = []
    monkeypatch.setattr(stop.log, "warn", lambda m: warned.append(m))

    stop.run()

    assert any("not removed" in m for m in warned)


def test_skips_network_removal_when_absent(monkeypatch):
    _quiet(monkeypatch)
    monkeypatch.setattr(stop.docker, "network_exists", lambda name: False)
    monkeypatch.setattr(
        stop.docker, "run", lambda *a: (_ for _ in ()).throw(AssertionError)
    )

    stop.run()  # must not raise / not attempt network rm


def test_clean_dangling_reports_reclaimed_amount(monkeypatch):
    _quiet(monkeypatch)
    monkeypatch.setattr(stop.config, "CLEAN_DANGLING", True)
    monkeypatch.setattr(stop.docker, "network_exists", lambda name: False)
    monkeypatch.setattr(
        stop.subprocess,
        "run",
        lambda argv, **kw: _FakeCompleted(
            stdout="Deleted Images:\nsome-image\nTotal reclaimed space: 42MB\n"
        ),
    )
    success = []
    monkeypatch.setattr(stop.log, "success", lambda m: success.append(m))

    stop.run()

    assert any("Total reclaimed space: 42MB" in m for m in success)


def test_clean_dangling_falls_back_to_unknown_when_no_match(monkeypatch):
    _quiet(monkeypatch)
    monkeypatch.setattr(stop.config, "CLEAN_DANGLING", True)
    monkeypatch.setattr(stop.docker, "network_exists", lambda name: False)
    monkeypatch.setattr(
        stop.subprocess, "run", lambda argv, **kw: _FakeCompleted(stdout="")
    )
    success = []
    monkeypatch.setattr(stop.log, "success", lambda m: success.append(m))

    stop.run()

    assert any("unknown" in m for m in success)


def test_clean_dangling_falls_back_to_unknown_on_oserror(monkeypatch):
    _quiet(monkeypatch)
    monkeypatch.setattr(stop.config, "CLEAN_DANGLING", True)
    monkeypatch.setattr(stop.docker, "network_exists", lambda name: False)

    def _raise(argv, **kw):
        raise OSError("docker not found")

    monkeypatch.setattr(stop.subprocess, "run", _raise)
    success = []
    monkeypatch.setattr(stop.log, "success", lambda m: success.append(m))

    stop.run()

    assert any("unknown" in m for m in success)


def test_clean_dangling_skipped_by_default(monkeypatch):
    _quiet(monkeypatch)
    monkeypatch.setattr(stop.docker, "network_exists", lambda name: False)
    monkeypatch.setattr(
        stop.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError)
    )

    stop.run()  # must not attempt the prune call at all
