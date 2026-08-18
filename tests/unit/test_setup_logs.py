"""Unit tests for the `logs` verb (scripts/setup/logs.py) -- previously only
the "unknown service" branch was gate-verified via shell; the Python module
itself had zero direct unit tests (16%). The streaming subprocess calls are
mocked; only their argv + return-code plumbing is asserted.
"""

from scripts.setup import logs


class _FakeCompleted:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


def test_run_streams_a_running_service_and_returns_its_exit_code(monkeypatch):
    monkeypatch.setattr(logs.docker, "container_name", lambda svc: "minder-api")
    monkeypatch.setattr(logs.docker, "running_names", lambda: ["minder-api"])
    captured = {}

    def _fake_run(argv):
        captured["argv"] = argv
        return _FakeCompleted(returncode=7)

    monkeypatch.setattr(logs.subprocess, "run", _fake_run)

    rc = logs.run(service="api", lines="250")

    assert rc == 7
    assert captured["argv"] == ["docker", "logs", "-f", "--tail", "250", "minder-api"]


def test_run_uses_default_tail_of_100_lines(monkeypatch):
    monkeypatch.setattr(logs.docker, "container_name", lambda svc: "minder-api")
    monkeypatch.setattr(logs.docker, "running_names", lambda: ["minder-api"])
    captured = {}

    def _fake_run(argv):
        captured["argv"] = argv
        return _FakeCompleted(returncode=0)

    monkeypatch.setattr(logs.subprocess, "run", _fake_run)

    logs.run(service="api")

    assert captured["argv"][4] == "100"


def test_run_reports_error_and_lists_running_when_service_not_running(
    monkeypatch, capfd
):
    monkeypatch.setattr(logs.docker, "container_name", lambda svc: "minder-api")
    monkeypatch.setattr(logs.docker, "running_names", lambda: [])
    monkeypatch.setattr(
        logs.subprocess,
        "run",
        lambda argv, **kw: _FakeCompleted(stdout="minder-postgres\nother-thing\n"),
    )

    rc = logs.run(service="api")

    out = capfd.readouterr().out
    assert rc == 1
    assert "No running container: minder-api" in out
    assert "Running containers:" in out
    assert "  minder-postgres" in out
    assert "other-thing" not in out


def test_run_streams_all_services_when_no_service_given(monkeypatch):
    captured = {}

    def _fake_compose(*args):
        captured["args"] = args
        return 3

    monkeypatch.setattr(logs.docker, "compose", _fake_compose)

    rc = logs.run()

    assert rc == 3
    assert captured["args"] == ("logs", "-f", "--tail", "50")


def test_print_running_list_shows_none_placeholder_when_nothing_matches(
    monkeypatch, capfd
):
    monkeypatch.setattr(
        logs.subprocess, "run", lambda argv, **kw: _FakeCompleted(stdout="unrelated\n")
    )

    logs._print_running_list()

    assert capfd.readouterr().out.strip() == "(none)"


def test_print_running_list_falls_back_to_none_when_docker_ps_fails(monkeypatch, capfd):
    def _raise(argv, **kw):
        raise OSError("docker not found")

    monkeypatch.setattr(logs.subprocess, "run", _raise)

    logs._print_running_list()

    assert capfd.readouterr().out.strip() == "(none)"
