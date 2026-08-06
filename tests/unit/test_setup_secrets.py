"""Unit tests for scripts/setup/secrets.py's sync_postgres_password().

A password containing a single quote used to break out of the SQL literal in
`ALTER USER minder PASSWORD '{new_password}';` -- fixed by passing it through
psql's `-v pwd=... -c "... :'pwd' ..."` substitution instead, which lets psql
itself apply correct SQL-literal quoting. No Docker: subprocess.run is stubbed.
"""

from pathlib import Path

from scripts.setup import secrets


def _stub_common(
    monkeypatch, *, env_file_exists=True, password="hex1234", running=True
):
    monkeypatch.setattr(secrets, "ENV_FILE", Path("/fake/.env"))
    monkeypatch.setattr(Path, "is_file", lambda self: env_file_exists)
    monkeypatch.setattr(secrets.env, "get", lambda key: password)
    monkeypatch.setattr(secrets.docker, "container_running", lambda svc: running)
    monkeypatch.setattr(secrets.docker, "container_name", lambda svc: "minder-postgres")
    for fn in ("error", "detail", "step", "warn", "success"):
        monkeypatch.setattr(secrets.log, fn, lambda *a, **k: None)


def test_password_passed_via_psql_variable_not_interpolated(monkeypatch):
    """The password with an embedded single quote must never appear inside the
    SQL text itself -- it must go through -v/:'pwd', which psql quotes safely."""
    seen_argv = []

    class _Result:
        returncode = 0

    def fake_run(argv, **kwargs):
        seen_argv.append(argv)
        return _Result()

    _stub_common(monkeypatch, password="abc'; DROP TABLE users; --")
    monkeypatch.setattr(secrets.subprocess, "run", fake_run)

    assert secrets.sync_postgres_password() == 0
    assert len(seen_argv) == 1
    argv = seen_argv[0]

    sql_arg = argv[argv.index("-c") + 1]
    # the raw password value (and its embedded quote/SQL) never reaches the SQL text --
    # only the fixed literal ":'pwd'" placeholder does; psql substitutes + quotes it.
    assert sql_arg == "ALTER USER minder PASSWORD :'pwd';"
    assert "DROP TABLE" not in sql_arg

    assert "-v" in argv
    assert argv[argv.index("-v") + 1] == "pwd=abc'; DROP TABLE users; --"


def test_missing_env_file_returns_error(monkeypatch):
    _stub_common(monkeypatch, env_file_exists=False)
    monkeypatch.setattr(
        secrets.subprocess,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("must not shell out when .env is missing")
        ),
    )
    assert secrets.sync_postgres_password() == 1


def test_container_not_running_returns_error(monkeypatch):
    _stub_common(monkeypatch, running=False)
    monkeypatch.setattr(
        secrets.subprocess,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("must not shell out when postgres isn't running")
        ),
    )
    assert secrets.sync_postgres_password() == 1
