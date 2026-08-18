"""Additional unit tests for scripts/dev/remote_ssh.py's remaining branches --
test_remote_ssh_arg_parsing.py already covers the --job/--no-cd/--raw/--no-pty
ordering regression. This file covers --list/--list-jobs, the no-argv usage
exit, the unknown-alias exit, --job-with-no-name, and --job-with-no-variant-
for-this-host's-shell. Same sys.path-insert convention as the existing file
(scripts/dev/ isn't a package); paramiko-gated via pytest.importorskip since
remote_lib imports it at module level.
"""

import importlib
import sys
from pathlib import Path

import pytest

pytest.importorskip("paramiko")

_DEV = Path(__file__).resolve().parents[2] / "scripts" / "dev"


@pytest.fixture
def remote_ssh_mod():
    saved_path = list(sys.path)
    saved_modules = {
        k: sys.modules[k] for k in ("remote_ssh", "remote_lib") if k in sys.modules
    }
    for k in ("remote_ssh", "remote_lib"):
        sys.modules.pop(k, None)
    sys.path.insert(0, str(_DEV))
    try:
        yield importlib.import_module("remote_ssh")
    finally:
        sys.path[:] = saved_path
        for k in ("remote_ssh", "remote_lib"):
            sys.modules.pop(k, None)
        sys.modules.update(saved_modules)


def _no_run(remote_ssh_mod, monkeypatch):
    monkeypatch.setattr(
        remote_ssh_mod.remote_lib,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not connect")),
    )


def test_list_prints_every_host_alias(remote_ssh_mod, monkeypatch, capsys):
    _no_run(remote_ssh_mod, monkeypatch)
    monkeypatch.setattr(remote_ssh_mod.remote_lib, "HOSTS", {"pi": {}, "hantal": {}})
    monkeypatch.setattr(sys, "argv", ["remote_ssh.py", "--list"])

    rc = remote_ssh_mod.main()

    out = capsys.readouterr().out
    assert rc == 0
    assert "pi" in out.splitlines()
    assert "hantal" in out.splitlines()


def test_list_short_flag_also_works(remote_ssh_mod, monkeypatch, capsys):
    _no_run(remote_ssh_mod, monkeypatch)
    monkeypatch.setattr(remote_ssh_mod.remote_lib, "HOSTS", {"pi": {}})
    monkeypatch.setattr(sys, "argv", ["remote_ssh.py", "-l"])

    rc = remote_ssh_mod.main()

    assert rc == 0
    assert "pi" in capsys.readouterr().out.splitlines()


def test_list_jobs_prints_every_job_name(remote_ssh_mod, monkeypatch, capsys):
    _no_run(remote_ssh_mod, monkeypatch)
    monkeypatch.setattr(remote_ssh_mod.remote_lib, "JOBS", {"update": {}, "status": {}})
    monkeypatch.setattr(sys, "argv", ["remote_ssh.py", "--list-jobs"])

    rc = remote_ssh_mod.main()

    out = capsys.readouterr().out
    assert rc == 0
    assert "update" in out.splitlines()
    assert "status" in out.splitlines()


def test_no_args_exits_with_usage(remote_ssh_mod, monkeypatch):
    _no_run(remote_ssh_mod, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["remote_ssh.py"])

    with pytest.raises(SystemExit) as exc_info:
        remote_ssh_mod.main()

    assert "usage:" in str(exc_info.value)


def test_unknown_alias_exits(remote_ssh_mod, monkeypatch):
    _no_run(remote_ssh_mod, monkeypatch)
    monkeypatch.setattr(remote_ssh_mod.remote_lib, "HOSTS", {"pi": {"shell": "raw"}})
    monkeypatch.setattr(sys, "argv", ["remote_ssh.py", "nope", "echo", "hi"])

    with pytest.raises(SystemExit) as exc_info:
        remote_ssh_mod.main()

    assert "unknown host alias" in str(exc_info.value)


def test_job_flag_with_no_name_exits(remote_ssh_mod, monkeypatch):
    _no_run(remote_ssh_mod, monkeypatch)
    monkeypatch.setattr(remote_ssh_mod.remote_lib, "HOSTS", {"pi": {"shell": "raw"}})
    monkeypatch.setattr(sys, "argv", ["remote_ssh.py", "pi", "--job"])

    with pytest.raises(SystemExit) as exc_info:
        remote_ssh_mod.main()

    assert "--job needs a name" in str(exc_info.value)


def test_unknown_job_name_message_lists_choices(remote_ssh_mod, monkeypatch):
    _no_run(remote_ssh_mod, monkeypatch)
    monkeypatch.setattr(remote_ssh_mod.remote_lib, "HOSTS", {"pi": {"shell": "raw"}})
    monkeypatch.setattr(remote_ssh_mod.remote_lib, "JOBS", {"update": {}})
    monkeypatch.setattr(sys, "argv", ["remote_ssh.py", "pi", "--job", "nope"])

    with pytest.raises(SystemExit) as exc_info:
        remote_ssh_mod.main()

    assert "unknown job 'nope'" in str(exc_info.value)
    assert "update" in str(exc_info.value)


def test_job_with_no_variant_for_this_hosts_shell_exits(remote_ssh_mod, monkeypatch):
    _no_run(remote_ssh_mod, monkeypatch)
    monkeypatch.setattr(remote_ssh_mod.remote_lib, "HOSTS", {"pi": {"shell": "raw"}})
    monkeypatch.setattr(
        remote_ssh_mod.remote_lib, "JOBS", {"update": {"powershell": ["echo hi"]}}
    )
    monkeypatch.setattr(sys, "argv", ["remote_ssh.py", "pi", "--job", "update"])

    with pytest.raises(SystemExit) as exc_info:
        remote_ssh_mod.main()

    assert "has no raw variant" in str(exc_info.value)


def test_no_cd_flag_alone_is_parsed(remote_ssh_mod, monkeypatch):
    calls = []
    monkeypatch.setattr(
        remote_ssh_mod.remote_lib,
        "run",
        lambda alias, cmds, no_cd=False, raw=False, no_pty=False: calls.append(
            (alias, cmds, no_cd, raw, no_pty)
        )
        or 0,
    )
    monkeypatch.setattr(remote_ssh_mod.remote_lib, "HOSTS", {"pi": {"shell": "raw"}})
    monkeypatch.setattr(sys, "argv", ["remote_ssh.py", "pi", "--no-cd", "echo hi"])

    remote_ssh_mod.main()

    assert calls == [("pi", ["echo hi"], True, False, False)]


def test_raw_flag_alone_is_parsed(remote_ssh_mod, monkeypatch):
    calls = []
    monkeypatch.setattr(
        remote_ssh_mod.remote_lib,
        "run",
        lambda alias, cmds, no_cd=False, raw=False, no_pty=False: calls.append(
            (alias, cmds, no_cd, raw, no_pty)
        )
        or 0,
    )
    monkeypatch.setattr(remote_ssh_mod.remote_lib, "HOSTS", {"pi": {"shell": "raw"}})
    monkeypatch.setattr(sys, "argv", ["remote_ssh.py", "pi", "--raw", "whoami"])

    remote_ssh_mod.main()

    assert calls == [("pi", ["whoami"], False, True, False)]


def test_no_command_defaults_to_echo_no_cmd(remote_ssh_mod, monkeypatch):
    calls = []
    monkeypatch.setattr(
        remote_ssh_mod.remote_lib,
        "run",
        lambda alias, cmds, no_cd=False, raw=False, no_pty=False: calls.append(cmds)
        or 0,
    )
    monkeypatch.setattr(remote_ssh_mod.remote_lib, "HOSTS", {"pi": {"shell": "raw"}})
    monkeypatch.setattr(sys, "argv", ["remote_ssh.py", "pi"])

    remote_ssh_mod.main()

    assert calls == [["echo no-cmd"]]
