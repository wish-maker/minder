"""Unit tests for scripts/dev/remote_ssh.py's argument parsing.

Regression guard for two real bugs found live, both from `--job` being
checked as a literal `argv[0]` in its own branch, entirely separate from the
`--no-cd`/`--raw`/`--no-pty` loop:

1. `remote_ssh.py pi --no-pty --job update` (flag first) fell through to the
   loop instead of the --job branch, consumed `--no-pty`, then tried to
   execute the literal leftover string "--job" as a shell command ("bash:
   line 1: --job: command not found").
2. `remote_ssh.py pi --job update --no-pty` (flag last) DID reach the --job
   branch, but that branch called `remote_lib.run(alias, cmds)` with no
   kwargs at all -- `--no-pty` was silently accepted and then dropped in
   every order, not just the first one.

`remote_lib.run` is monkeypatched so no real SSH connection is attempted.

scripts/dev/ isn't a package (`remote_ssh.py` does a bare `import remote_lib`,
expecting `scripts/dev/` on sys.path) -- loaded by path + sys.path insert, same
convention as this repo's other hyphenated/non-package directories.
"""

import importlib
import sys
from pathlib import Path

import pytest

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


def _run_capture(remote_ssh_mod, monkeypatch, argv):
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
    monkeypatch.setattr(
        remote_ssh_mod.remote_lib,
        "JOBS",
        {"update": {"raw": ["git pull", "bash setup.sh update"]}},
    )
    monkeypatch.setattr(sys, "argv", ["remote_ssh.py", *argv])
    remote_ssh_mod.main()
    return calls


def test_no_pty_before_job_runs_the_job(remote_ssh_mod, monkeypatch):
    """The exact failing invocation: --no-pty before --job."""
    calls = _run_capture(
        remote_ssh_mod, monkeypatch, ["pi", "--no-pty", "--job", "update"]
    )
    assert calls == [("pi", ["git pull", "bash setup.sh update"], False, False, True)]


def test_job_before_no_pty_also_works(remote_ssh_mod, monkeypatch):
    """This order used to reach the --job branch fine but still dropped
    --no-pty silently -- both orders must now actually apply it."""
    calls = _run_capture(
        remote_ssh_mod, monkeypatch, ["pi", "--job", "update", "--no-pty"]
    )
    assert calls == [("pi", ["git pull", "bash setup.sh update"], False, False, True)]


def test_plain_job_no_flags(remote_ssh_mod, monkeypatch):
    calls = _run_capture(remote_ssh_mod, monkeypatch, ["pi", "--job", "update"])
    assert calls == [("pi", ["git pull", "bash setup.sh update"], False, False, False)]


def test_inline_commands_with_no_pty_unaffected(remote_ssh_mod, monkeypatch):
    """The non-job path (inline commands) must still work exactly as before."""
    calls = _run_capture(remote_ssh_mod, monkeypatch, ["pi", "--no-pty", "echo hi"])
    assert calls == [("pi", ["echo hi"], False, False, True)]


def test_unknown_job_name_exits(remote_ssh_mod, monkeypatch):
    monkeypatch.setattr(remote_ssh_mod.remote_lib, "HOSTS", {"pi": {"shell": "raw"}})
    monkeypatch.setattr(remote_ssh_mod.remote_lib, "JOBS", {"update": {"raw": []}})
    monkeypatch.setattr(sys, "argv", ["remote_ssh.py", "pi", "--job", "nope"])
    with pytest.raises(SystemExit):
        remote_ssh_mod.main()
