"""Unit tests for the `shell` verb (scripts/setup/shell.py) -- only the two
error branches were gate-verified via shell (scripts/gate/shell_verify.sh);
the Python module itself had zero direct unit tests (16%). The interactive
`docker exec -it` calls are mocked -- only argv + return-code plumbing and
the bash/sh probe fallback are exercised.
"""

from scripts.setup import shell


class _FakeCompleted:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


def _routed_run(routes, default=None):
    def _run(argv, **kw):
        for key, result in routes.items():
            if list(argv) == list(key):
                return result
        return default if default is not None else _FakeCompleted()

    return _run


def test_run_reports_container_not_running(monkeypatch):
    monkeypatch.setattr(shell.docker, "container_name", lambda svc: "minder-api")
    monkeypatch.setattr(shell.docker, "running_names", lambda: [])

    rc = shell.run(service="api")

    assert rc == 1


def test_run_opens_bash_when_probe_succeeds(monkeypatch):
    monkeypatch.setattr(shell.docker, "container_name", lambda svc: "minder-api")
    monkeypatch.setattr(shell.docker, "running_names", lambda: ["minder-api"])
    exec_argv = ["docker", "exec", "-it", "minder-api", "bash"]
    routes = {
        ("docker", "exec", "-it", "minder-api", "bash", "--version"): _FakeCompleted(
            returncode=0
        ),
        tuple(exec_argv): _FakeCompleted(returncode=42),
    }
    monkeypatch.setattr(shell.subprocess, "run", _routed_run(routes))

    rc = shell.run(service="api")

    assert rc == 42


def test_run_falls_back_to_sh_when_bash_probe_fails(monkeypatch):
    monkeypatch.setattr(shell.docker, "container_name", lambda svc: "minder-api")
    monkeypatch.setattr(shell.docker, "running_names", lambda: ["minder-api"])
    exec_argv = ["docker", "exec", "-it", "minder-api", "sh"]
    routes = {
        ("docker", "exec", "-it", "minder-api", "bash", "--version"): _FakeCompleted(
            returncode=1
        ),
        tuple(exec_argv): _FakeCompleted(returncode=0),
    }
    calls = []
    real_routed = _routed_run(routes)

    def _tracking_run(argv, **kw):
        calls.append(list(argv))
        return real_routed(argv, **kw)

    monkeypatch.setattr(shell.subprocess, "run", _tracking_run)

    rc = shell.run(service="api")

    assert rc == 0
    assert exec_argv in calls


def test_run_without_service_and_noninteractive_errors_without_prompting(
    monkeypatch, capfd
):
    monkeypatch.setattr(shell.config, "INTERACTIVE", False)
    monkeypatch.setattr(
        shell.subprocess, "run", lambda argv, **kw: _FakeCompleted(stdout="")
    )

    rc = shell.run()

    out = capfd.readouterr().out
    assert rc == 1
    assert "Specify a service" in out
    assert "Running containers:" in out


def test_run_without_service_and_interactive_reads_service_from_stdin(monkeypatch):
    monkeypatch.setattr(shell.config, "INTERACTIVE", True)
    monkeypatch.setattr(
        shell.subprocess, "run", lambda argv, **kw: _FakeCompleted(stdout="")
    )
    monkeypatch.setattr(shell.sys.stdin, "readline", lambda: "api\n")
    monkeypatch.setattr(shell.docker, "container_name", lambda svc: f"minder-{svc}")
    monkeypatch.setattr(shell.docker, "running_names", lambda: [])

    rc = shell.run()

    assert rc == 1


def test_print_running_list_stripped_shows_indented_names_without_prefix(
    monkeypatch, capfd
):
    monkeypatch.setattr(
        shell.subprocess,
        "run",
        lambda argv, **kw: _FakeCompleted(stdout="minder-postgres\nother-thing\n"),
    )

    shell._print_running_list_stripped()

    out = capfd.readouterr().out
    assert "  postgres" in out
    assert "other-thing" not in out


def test_print_running_list_stripped_shows_none_when_nothing_matches(
    monkeypatch, capfd
):
    monkeypatch.setattr(
        shell.subprocess, "run", lambda argv, **kw: _FakeCompleted(stdout="unrelated\n")
    )

    shell._print_running_list_stripped()

    assert capfd.readouterr().out.strip() == "(none)"


def test_print_running_list_stripped_falls_back_when_docker_ps_fails(
    monkeypatch, capfd
):
    def _raise(argv, **kw):
        raise OSError("docker not found")

    monkeypatch.setattr(shell.subprocess, "run", _raise)

    shell._print_running_list_stripped()

    assert capfd.readouterr().out.strip() == "(none)"


def test_run_without_service_uses_bold_header_when_colors_on(monkeypatch, capfd):
    monkeypatch.setattr(shell.config, "INTERACTIVE", False)
    monkeypatch.setattr(shell.log, "_colors_on", lambda: True)
    monkeypatch.setattr(
        shell.subprocess, "run", lambda argv, **kw: _FakeCompleted(stdout="")
    )

    shell.run()

    out = capfd.readouterr().out
    assert shell.log._BOLD in out
    assert "Running containers:" in out
