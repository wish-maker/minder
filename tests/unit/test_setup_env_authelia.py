"""Unit tests for scripts/setup/env.py's render_authelia_config() and
render_users_database() (#473).

Found live on the Pi: Docker auto-creates a missing bind-mount SOURCE path as
a directory the first time a container using it is created. If that races
ahead of render_authelia_config()'s first successful write (or a prior render
crashed before writing), configuration.rendered.yml ends up as an empty
directory instead of a file -- every later `docker start minder-authelia`
then fails ("not a directory") against it, and the OLD code's write_text()
call wasn't even guarded by the same try/except OSError wrapping the reads
just above it, so a genuine write failure would crash the whole prepare_env()
call instead of degrading gracefully like a read failure does.
render_users_database() shares this exact same self-heal shape.

No Docker: _hash_oidc_client_secret / _hash_admin_password are stubbed (they
shell out to Authelia's own CLI in a throwaway container).
"""

from pathlib import Path

import pytest

from scripts.setup import env


@pytest.fixture(autouse=True)
def _no_secret_hash(monkeypatch):
    monkeypatch.setattr(env, "_hash_oidc_client_secret", lambda: "")
    monkeypatch.setattr(env, "_hash_admin_password", lambda: "")


@pytest.fixture
def _config_paths(tmp_path, monkeypatch):
    src = tmp_path / "configuration.yml"
    src.write_text(
        "some_key: __MINDER_OIDC_ISSUER_KEY_PEM__\n",
        encoding="utf-8",
    )
    issuer_key = tmp_path / "oidc_issuer.pem"
    issuer_key.write_text(
        "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n"
    )
    rendered = tmp_path / "configuration.rendered.yml"

    monkeypatch.setattr(env, "_AUTHELIA_CONFIG_SRC", src)
    monkeypatch.setattr(env, "_OIDC_ISSUER_KEY", issuer_key)
    monkeypatch.setattr(env, "_AUTHELIA_CONFIG_RENDERED", rendered)
    return rendered


def test_render_authelia_config_writes_a_real_file(_config_paths):
    env.render_authelia_config()

    assert _config_paths.is_file()
    content = _config_paths.read_text(encoding="utf-8")
    assert "__MINDER_OIDC_ISSUER_KEY_PEM__" not in content
    assert "-----BEGIN PRIVATE KEY-----" in content


def test_render_authelia_config_self_heals_a_stray_directory(_config_paths):
    """The exact bug found on the Pi: the rendered path is a directory
    (Docker's auto-create-on-missing-bind-mount behavior), not a file."""
    _config_paths.mkdir()
    assert _config_paths.is_dir()

    env.render_authelia_config()

    assert (
        _config_paths.is_file()
    ), "stray directory must be replaced with the rendered file"
    assert "-----BEGIN PRIVATE KEY-----" in _config_paths.read_text(encoding="utf-8")


def test_render_authelia_config_logs_and_returns_on_read_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(env, "_AUTHELIA_CONFIG_SRC", tmp_path / "does-not-exist.yml")
    monkeypatch.setattr(env, "_OIDC_ISSUER_KEY", tmp_path / "also-missing.pem")
    rendered = tmp_path / "configuration.rendered.yml"
    monkeypatch.setattr(env, "_AUTHELIA_CONFIG_RENDERED", rendered)

    env.render_authelia_config()  # must not raise

    assert not rendered.exists()


def test_render_authelia_config_logs_and_returns_on_write_failure(
    monkeypatch, _config_paths
):
    """A genuine write failure (e.g. permission denied) degrades like a read
    failure does, instead of crashing prepare_env() -- the old code's
    write_text() call wasn't inside the try/except at all."""

    def _boom(self, *args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "write_text", _boom)

    env.render_authelia_config()  # must not raise


# ── render_users_database() (#473) ───────────────────────────────────────────


@pytest.fixture
def _users_db_paths(tmp_path, monkeypatch):
    src = tmp_path / "users_database.yml"
    src.write_text(
        'users:\n  admin:\n    password: "__MINDER_AUTHELIA_ADMIN_PASSWORD_HASH__"\n',
        encoding="utf-8",
    )
    rendered = tmp_path / "users_database.rendered.yml"

    monkeypatch.setattr(env, "_USERS_DB_SRC", src)
    monkeypatch.setattr(env, "_USERS_DB_RENDERED", rendered)
    return rendered


def test_render_users_database_substitutes_the_real_hash(_users_db_paths, monkeypatch):
    monkeypatch.setattr(env, "_hash_admin_password", lambda: "$argon2id$fake$hash")

    env.render_users_database()

    content = _users_db_paths.read_text(encoding="utf-8")
    assert "__MINDER_AUTHELIA_ADMIN_PASSWORD_HASH__" not in content
    assert "$argon2id$fake$hash" in content


def test_render_users_database_still_writes_a_file_when_hashing_fails(
    _users_db_paths,
):
    """Hashing failing (no docker, etc.) must NOT skip writing the rendered
    file -- a missing file here is exactly the Docker
    auto-creates-a-missing-bind-mount-as-a-directory bug already fixed for
    configuration.rendered.yml. The placeholder is left in place instead,
    which fails loudly and debuggably (Authelia rejects the literal string
    as an invalid hash) rather than silently as a missing-file crash."""
    env.render_users_database()  # _hash_admin_password stubbed to "" by autouse fixture

    assert _users_db_paths.is_file()
    assert "__MINDER_AUTHELIA_ADMIN_PASSWORD_HASH__" in _users_db_paths.read_text(
        encoding="utf-8"
    )


def test_render_users_database_self_heals_a_stray_directory(
    _users_db_paths, monkeypatch
):
    """The exact bug found on the Pi for configuration.rendered.yml, same
    shape here: the rendered path is a directory (Docker's
    auto-create-on-missing-bind-mount behavior), not a file."""
    monkeypatch.setattr(env, "_hash_admin_password", lambda: "$argon2id$fake$hash")
    _users_db_paths.mkdir()
    assert _users_db_paths.is_dir()

    env.render_users_database()

    assert (
        _users_db_paths.is_file()
    ), "stray directory must be replaced with the rendered file"
    assert "$argon2id$fake$hash" in _users_db_paths.read_text(encoding="utf-8")


def test_render_users_database_logs_and_returns_on_read_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(env, "_USERS_DB_SRC", tmp_path / "does-not-exist.yml")
    rendered = tmp_path / "users_database.rendered.yml"
    monkeypatch.setattr(env, "_USERS_DB_RENDERED", rendered)

    env.render_users_database()  # must not raise

    assert not rendered.exists()
