"""Unit tests for scripts/setup/env.py's render_authelia_config().

Found live on the Pi: Docker auto-creates a missing bind-mount SOURCE path as
a directory the first time a container using it is created. If that races
ahead of render_authelia_config()'s first successful write (or a prior render
crashed before writing), configuration.rendered.yml ends up as an empty
directory instead of a file -- every later `docker start minder-authelia`
then fails ("not a directory") against it, and the OLD code's write_text()
call wasn't even guarded by the same try/except OSError wrapping the reads
just above it, so a genuine write failure would crash the whole prepare_env()
call instead of degrading gracefully like a read failure does.

No Docker: _hash_oidc_client_secret is stubbed (it shells out to Authelia's
own CLI in a throwaway container).
"""

from pathlib import Path

import pytest

from scripts.setup import env


@pytest.fixture(autouse=True)
def _no_secret_hash(monkeypatch):
    monkeypatch.setattr(env, "_hash_oidc_client_secret", lambda: "")


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
