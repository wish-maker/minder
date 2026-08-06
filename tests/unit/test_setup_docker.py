"""Unit tests for scripts/setup/docker.py's wait_postgres_ready() (#351).

#351: pg_isready with no -h defaults to the local Unix socket, which the
postgres image's docker-entrypoint.sh's TEMPORARY bootstrap server (used only
to run docker-entrypoint-initdb.d/init.sql) also accepts connections on --
only the REAL, final server additionally binds TCP. Without forcing TCP,
wait_postgres_ready() returned True too early (against the temporary server),
letting infra.py's initialize_database() race against init.sql and silently
lose some CREATE DATABASE calls (confirmed live on the Pi: minder_authelia/
minder_schemaregistry/news_db/crypto_db never got created on a fresh
install, crash-looping authelia/schema-registry forever).

No Docker: subprocess.run is stubbed.
"""

from scripts.setup import docker


def test_pg_isready_is_forced_over_tcp(monkeypatch):
    seen_argv = []

    class _Result:
        returncode = 0

    def fake_run(argv, **kwargs):
        seen_argv.append(argv)
        return _Result()

    monkeypatch.setattr(docker.subprocess, "run", fake_run)
    monkeypatch.setattr(docker.log, "spinner_start", lambda *a, **k: None)
    monkeypatch.setattr(docker.log, "spinner_stop", lambda *a, **k: None)
    monkeypatch.setattr(docker.log, "success", lambda *a, **k: None)

    assert docker.wait_postgres_ready(timeout=5) is True
    assert len(seen_argv) == 1
    argv = seen_argv[0]
    assert "pg_isready" in argv
    # -h 127.0.0.1 must be present, and specifically BEFORE -U (not load-bearing
    # order-wise, but this pins the exact invocation this fix relies on).
    assert "-h" in argv
    assert argv[argv.index("-h") + 1] == "127.0.0.1"
