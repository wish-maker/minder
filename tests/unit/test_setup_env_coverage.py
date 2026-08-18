"""Unit tests for scripts/setup/env.py's remaining surface -- get(), gen_secret,
sync_compose_env, sync_telegraf_config, ensure_bundles_state_file,
ensure_oidc_issuer_key, _hash_oidc_client_secret, _hash_admin_password,
fill_env_secrets (full backfill -- test_setup_env_fill_secrets.py deliberately
scoped to just the admin-password print-once behavior), write_default_env,
ensure_docker_gid, and prepare_env's orchestration. render_authelia_config /
render_users_database / _upsert_env_key already have dedicated test files.

No real Docker/subprocess calls: docker.container_running and
subprocess.run are mocked throughout.
"""

import sys

import pytest

from scripts.setup import env

_posix_perms_only = pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX file modes (0o600) aren't representable on Windows/NTFS",
)


class _FakeCompleted:
    def __init__(self, returncode=0, stdout=b"", text_stdout=""):
        self.returncode = returncode
        self.stdout = stdout if stdout else text_stdout


# ── get() ──────────────────────────────────────────────────────────────────────


def test_get_returns_value_after_first_equals(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("KEY=value=with=equals\nOTHER=x\n", encoding="utf-8")
    monkeypatch.setattr(env, "ENV_FILE", env_file)

    assert env.get("KEY") == "value=with=equals"


def test_get_joins_multiple_matches_with_newline(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("KEY=a\nKEY=b\n", encoding="utf-8")
    monkeypatch.setattr(env, "ENV_FILE", env_file)

    assert env.get("KEY") == "a\nb"


def test_get_returns_empty_when_key_absent(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("OTHER=x\n", encoding="utf-8")
    monkeypatch.setattr(env, "ENV_FILE", env_file)

    assert env.get("KEY") == ""


def test_get_returns_empty_on_oserror(monkeypatch, tmp_path):
    monkeypatch.setattr(env, "ENV_FILE", tmp_path / "does-not-exist.env")
    assert env.get("KEY") == ""


# ── gen_secret ─────────────────────────────────────────────────────────────────


def test_gen_secret_length_and_charset():
    secret = env.gen_secret(16)
    assert len(secret) == 32
    assert all(c in "0123456789abcdef" for c in secret)


def test_gen_secret_is_random_across_calls():
    assert env.gen_secret(16) != env.gen_secret(16)


# ── sync_compose_env ───────────────────────────────────────────────────────────


def test_sync_compose_env_writes_banner_and_body(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("KEY=value\n", encoding="utf-8")
    compose_env = tmp_path / "docker" / "compose.env"
    monkeypatch.setattr(env, "ENV_FILE", env_file)
    monkeypatch.setattr(env, "COMPOSE_ENV_FILE", compose_env)

    env.sync_compose_env()

    content = compose_env.read_text(encoding="utf-8")
    assert "DO NOT EDIT" in content
    assert content.endswith("KEY=value\n")


def test_sync_compose_env_tolerates_missing_source(monkeypatch, tmp_path):
    monkeypatch.setattr(env, "ENV_FILE", tmp_path / "missing.env")
    compose_env = tmp_path / "docker" / "compose.env"
    monkeypatch.setattr(env, "COMPOSE_ENV_FILE", compose_env)

    env.sync_compose_env()  # must not raise

    assert "DO NOT EDIT" in compose_env.read_text(encoding="utf-8")


def test_sync_compose_env_tolerates_chmod_oserror(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    compose_env = tmp_path / "compose.env"
    monkeypatch.setattr(env, "ENV_FILE", env_file)
    monkeypatch.setattr(env, "COMPOSE_ENV_FILE", compose_env)
    monkeypatch.setattr(
        env.Path, "chmod", lambda self, mode: (_ for _ in ()).throw(OSError("nope"))
    )

    env.sync_compose_env()  # must not raise

    assert "DO NOT EDIT" in compose_env.read_text(encoding="utf-8")


@_posix_perms_only
def test_sync_compose_env_chmods_600(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    compose_env = tmp_path / "compose.env"
    monkeypatch.setattr(env, "ENV_FILE", env_file)
    monkeypatch.setattr(env, "COMPOSE_ENV_FILE", compose_env)

    env.sync_compose_env()

    assert (compose_env.stat().st_mode & 0o777) == 0o600


# ── sync_telegraf_config ───────────────────────────────────────────────────────


def test_sync_telegraf_config_seeds_from_template_when_absent(monkeypatch, tmp_path):
    template = tmp_path / "telegraf.conf"
    template.write_text("static config\n", encoding="utf-8")
    runtime = tmp_path / "runtime" / "telegraf.conf"
    monkeypatch.setattr(env.config, "TELEGRAF_TEMPLATE", template)
    monkeypatch.setattr(env.config, "TELEGRAF_RUNTIME", runtime)

    env.sync_telegraf_config()

    assert runtime.read_text(encoding="utf-8") == "static config\n"


def test_sync_telegraf_config_leaves_an_existing_runtime_file_alone(
    monkeypatch, tmp_path
):
    template = tmp_path / "telegraf.conf"
    template.write_text("new template\n", encoding="utf-8")
    runtime = tmp_path / "runtime.conf"
    runtime.write_text("already has a managed region\n", encoding="utf-8")
    monkeypatch.setattr(env.config, "TELEGRAF_TEMPLATE", template)
    monkeypatch.setattr(env.config, "TELEGRAF_RUNTIME", runtime)

    env.sync_telegraf_config()

    assert runtime.read_text(encoding="utf-8") == "already has a managed region\n"


def test_sync_telegraf_config_tolerates_missing_template(monkeypatch, tmp_path):
    monkeypatch.setattr(env.config, "TELEGRAF_TEMPLATE", tmp_path / "missing.conf")
    runtime = tmp_path / "runtime.conf"
    monkeypatch.setattr(env.config, "TELEGRAF_RUNTIME", runtime)

    env.sync_telegraf_config()  # must not raise

    assert not runtime.exists()


# ── ensure_bundles_state_file ──────────────────────────────────────────────────


def test_ensure_bundles_state_file_seeds_empty_object_when_absent(
    monkeypatch, tmp_path
):
    state = tmp_path / "bundles.state.json"
    monkeypatch.setattr(env.config, "BUNDLES_STATE", state)

    env.ensure_bundles_state_file()

    assert state.read_text(encoding="utf-8") == "{}\n"


@_posix_perms_only
def test_ensure_bundles_state_file_is_world_writable(monkeypatch, tmp_path):
    state = tmp_path / "bundles.state.json"
    monkeypatch.setattr(env.config, "BUNDLES_STATE", state)

    env.ensure_bundles_state_file()

    assert (state.stat().st_mode & 0o777) == 0o666


def test_ensure_bundles_state_file_never_clobbers_existing_content(
    monkeypatch, tmp_path
):
    state = tmp_path / "bundles.state.json"
    state.write_text('{"monitoring": false}\n', encoding="utf-8")
    monkeypatch.setattr(env.config, "BUNDLES_STATE", state)

    env.ensure_bundles_state_file()

    assert state.read_text(encoding="utf-8") == '{"monitoring": false}\n'


def test_ensure_bundles_state_file_tolerates_oserror(monkeypatch, tmp_path):
    state = tmp_path / "nonexistent-dir" / "bundles.state.json"
    monkeypatch.setattr(env.config, "BUNDLES_STATE", state)

    def _boom(self, *a, **k):
        raise OSError("permission denied")

    monkeypatch.setattr(env.Path, "mkdir", _boom)

    env.ensure_bundles_state_file()  # must not raise


# ── ensure_oidc_issuer_key ─────────────────────────────────────────────────────


def test_ensure_oidc_issuer_key_skips_when_already_present(monkeypatch, tmp_path):
    key = tmp_path / "oidc_issuer.pem"
    key.write_text("existing key\n", encoding="utf-8")
    monkeypatch.setattr(env, "_OIDC_ISSUER_KEY", key)
    monkeypatch.setattr(
        env.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError)
    )

    env.ensure_oidc_issuer_key()

    assert key.read_text(encoding="utf-8") == "existing key\n"


def test_ensure_oidc_issuer_key_generates_via_docker(monkeypatch, tmp_path):
    key = tmp_path / "sub" / "oidc_issuer.pem"
    monkeypatch.setattr(env, "_OIDC_ISSUER_KEY", key)
    pem = b"-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n"
    monkeypatch.setattr(
        env.subprocess, "run", lambda *a, **k: _FakeCompleted(stdout=pem)
    )

    env.ensure_oidc_issuer_key()

    assert key.read_bytes() == pem


def test_ensure_oidc_issuer_key_warns_on_unexpected_output(
    monkeypatch, tmp_path, capfd
):
    key = tmp_path / "oidc_issuer.pem"
    monkeypatch.setattr(env, "_OIDC_ISSUER_KEY", key)
    monkeypatch.setattr(
        env.subprocess, "run", lambda *a, **k: _FakeCompleted(stdout=b"not a pem")
    )

    env.ensure_oidc_issuer_key()

    assert not key.exists()
    assert "unexpected output" in capfd.readouterr().out


@pytest.mark.parametrize(
    "exc",
    [
        OSError("docker not found"),
        env.subprocess.CalledProcessError(1, "docker"),
        env.subprocess.TimeoutExpired(cmd="docker", timeout=120),
    ],
)
def test_ensure_oidc_issuer_key_warns_on_subprocess_failure(
    monkeypatch, tmp_path, capfd, exc
):
    key = tmp_path / "oidc_issuer.pem"
    monkeypatch.setattr(env, "_OIDC_ISSUER_KEY", key)

    def _raise(*a, **k):
        raise exc

    monkeypatch.setattr(env.subprocess, "run", _raise)

    env.ensure_oidc_issuer_key()

    assert not key.exists()
    assert "Could not generate OIDC issuer key" in capfd.readouterr().out


# ── _hash_oidc_client_secret / _hash_admin_password ───────────────────────────


def test_hash_oidc_client_secret_returns_empty_when_secret_unset(monkeypatch):
    monkeypatch.setattr(env, "get", lambda key: "")
    monkeypatch.setattr(
        env.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError)
    )
    assert env._hash_oidc_client_secret() == ""


def test_hash_oidc_client_secret_parses_digest_line(monkeypatch):
    monkeypatch.setattr(env, "get", lambda key: "the-secret")
    monkeypatch.setattr(
        env.subprocess,
        "run",
        lambda *a, **k: _FakeCompleted(text_stdout="Digest: $argon2id$fake$hash\n"),
    )
    assert env._hash_oidc_client_secret() == "$argon2id$fake$hash"


def test_hash_oidc_client_secret_returns_raw_line_without_colon(monkeypatch):
    monkeypatch.setattr(env, "get", lambda key: "the-secret")
    monkeypatch.setattr(
        env.subprocess, "run", lambda *a, **k: _FakeCompleted(text_stdout="just-a-hash")
    )
    assert env._hash_oidc_client_secret() == "just-a-hash"


def test_hash_oidc_client_secret_warns_on_failure(monkeypatch, capfd):
    monkeypatch.setattr(env, "get", lambda key: "the-secret")

    def _raise(*a, **k):
        raise OSError("boom")

    monkeypatch.setattr(env.subprocess, "run", _raise)

    assert env._hash_oidc_client_secret() == ""
    assert "Could not hash OIDC client secret" in capfd.readouterr().out


def test_hash_admin_password_returns_empty_when_unset(monkeypatch):
    monkeypatch.setattr(env, "get", lambda key: "")
    assert env._hash_admin_password() == ""


def test_hash_admin_password_parses_digest_line(monkeypatch):
    monkeypatch.setattr(env, "get", lambda key: "the-password")
    monkeypatch.setattr(
        env.subprocess,
        "run",
        lambda *a, **k: _FakeCompleted(text_stdout="Digest: $argon2id$fake$hash2\n"),
    )
    assert env._hash_admin_password() == "$argon2id$fake$hash2"


def test_hash_admin_password_warns_on_failure(monkeypatch, capfd):
    monkeypatch.setattr(env, "get", lambda key: "the-password")

    def _raise(*a, **k):
        raise env.subprocess.CalledProcessError(1, "docker")

    monkeypatch.setattr(env.subprocess, "run", _raise)

    assert env._hash_admin_password() == ""
    assert "Could not hash Authelia admin password" in capfd.readouterr().out


# ── _chmod_600 / _live_core / _upsert_env_key read failure ────────────────────


@_posix_perms_only
def test_chmod_600_sets_the_mode(tmp_path):
    target = tmp_path / "secret-file"
    target.write_text("", encoding="utf-8")
    target.chmod(0o644)

    env._chmod_600(target)

    assert (target.stat().st_mode & 0o777) == 0o600


def test_chmod_600_tolerates_oserror(tmp_path):
    env._chmod_600(tmp_path / "does-not-exist")  # must not raise


def test_live_core_returns_none_when_nothing_running(monkeypatch):
    monkeypatch.setattr(env.docker, "container_running", lambda svc: False)
    assert env._live_core() is None


def test_live_core_returns_first_running_stateful_core(monkeypatch):
    monkeypatch.setattr(env.docker, "container_running", lambda svc: svc == "neo4j")
    assert env._live_core() == "neo4j"


def test_upsert_env_key_returns_silently_on_read_oserror(monkeypatch, tmp_path):
    env_file = tmp_path / "does-not-exist" / ".env"
    monkeypatch.setattr(env, "ENV_FILE", env_file)
    monkeypatch.setattr(env, "ENV_LOCK", tmp_path / ".env.lock")

    env._upsert_env_key("KEY", "value")  # must not raise

    assert not env_file.exists()


# ── fill_env_secrets (full backfill) ──────────────────────────────────────────


@pytest.fixture
def _secrets_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(env, "ENV_FILE", env_file)
    monkeypatch.setattr(env, "ENV_LOCK", tmp_path / ".env.lock")
    monkeypatch.setattr(env, "SECRET_SPEC", {"POSTGRES_PASSWORD": "8"})
    monkeypatch.setattr(env, "_live_core", lambda: None)
    return env_file


def test_fill_env_secrets_generates_a_missing_key(_secrets_env, capfd):
    env.fill_env_secrets()

    value = env.get("POSTGRES_PASSWORD")
    assert len(value) == 16  # gen_secret(8) -> 16 hex chars
    assert "1 secret(s) generated" in capfd.readouterr().out


def test_fill_env_secrets_fills_a_placeholder_value(_secrets_env):
    _secrets_env.write_text("POSTGRES_PASSWORD=CHANGEME\n", encoding="utf-8")

    env.fill_env_secrets()

    value = env.get("POSTGRES_PASSWORD")
    assert value != "CHANGEME"
    assert len(value) == 16


def test_fill_env_secrets_replaces_the_existing_line_in_place(_secrets_env):
    _secrets_env.write_text(
        "BEFORE=1\nPOSTGRES_PASSWORD=CHANGEME\nAFTER=2\n", encoding="utf-8"
    )

    env.fill_env_secrets()

    lines = _secrets_env.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "BEFORE=1"
    assert lines[2] == "AFTER=2"
    assert lines[1].startswith("POSTGRES_PASSWORD=")
    assert lines[1] != "POSTGRES_PASSWORD=CHANGEME"


def test_fill_env_secrets_appends_when_key_entirely_absent(_secrets_env):
    _secrets_env.write_text("OTHER_KEY=1\n", encoding="utf-8")

    env.fill_env_secrets()

    lines = _secrets_env.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "OTHER_KEY=1"
    assert any(ln.startswith("POSTGRES_PASSWORD=") for ln in lines[1:])


def test_fill_env_secrets_silent_noop_when_fully_populated(_secrets_env, capfd):
    _secrets_env.write_text(
        "POSTGRES_PASSWORD=already-a-real-secret\n", encoding="utf-8"
    )

    env.fill_env_secrets()

    assert capfd.readouterr().out == ""
    assert env.get("POSTGRES_PASSWORD") == "already-a-real-secret"


def test_fill_env_secrets_prefixed_spec_bare_prefix_counts_as_unset(
    tmp_path, monkeypatch
):
    env_file = tmp_path / ".env"
    env_file.write_text("NEO4J_AUTH=neo4j/\n", encoding="utf-8")
    monkeypatch.setattr(env, "ENV_FILE", env_file)
    monkeypatch.setattr(env, "ENV_LOCK", tmp_path / ".env.lock")
    monkeypatch.setattr(env, "SECRET_SPEC", {"NEO4J_AUTH": "16:neo4j/"})
    monkeypatch.setattr(env, "_live_core", lambda: None)

    env.fill_env_secrets()

    value = env.get("NEO4J_AUTH")
    assert value.startswith("neo4j/")
    assert value != "neo4j/"


def test_fill_env_secrets_backs_up_env_before_rewriting(_secrets_env):
    env.fill_env_secrets()

    backups = list(_secrets_env.parent.glob(".env.backup-*"))
    assert len(backups) == 1


@_posix_perms_only
def test_fill_env_secrets_backup_is_chmod_600(_secrets_env):
    env.fill_env_secrets()
    backup = next(_secrets_env.parent.glob(".env.backup-*"))
    assert (backup.stat().st_mode & 0o777) == 0o600


def test_fill_env_secrets_refuses_when_stack_is_live(monkeypatch, _secrets_env, capfd):
    monkeypatch.setattr(env, "_live_core", lambda: "postgres")
    monkeypatch.delenv("MINDER_ALLOW_SECRET_REGEN", raising=False)

    with pytest.raises(SystemExit):
        env.fill_env_secrets()

    out = capfd.readouterr().out
    assert "Refusing to regenerate" in out
    assert "postgres" in out
    assert env.get("POSTGRES_PASSWORD") == ""


def test_fill_env_secrets_allow_regen_overrides_the_live_guard(
    monkeypatch, _secrets_env
):
    monkeypatch.setattr(env, "_live_core", lambda: "postgres")
    monkeypatch.setenv("MINDER_ALLOW_SECRET_REGEN", "1")

    env.fill_env_secrets()  # must not raise

    assert env.get("POSTGRES_PASSWORD") != ""


def test_fill_env_secrets_tolerates_read_text_oserror(tmp_path, monkeypatch):
    """A transient read failure (raw="") must not crash -- every SECRET_SPEC
    key is then treated as missing and freshly generated. Isolates just the
    read-text failure (read_bytes, used by the backup step right after, is
    left working normally)."""
    env_file = tmp_path / ".env"
    env_file.write_text("POSTGRES_PASSWORD=already-set\n", encoding="utf-8")
    monkeypatch.setattr(env, "ENV_FILE", env_file)
    monkeypatch.setattr(env, "ENV_LOCK", tmp_path / ".env.lock")
    monkeypatch.setattr(env, "SECRET_SPEC", {"POSTGRES_PASSWORD": "8"})
    monkeypatch.setattr(env, "_live_core", lambda: None)

    real_read_text = env.Path.read_text

    def _boom(self, *a, **k):
        if self == env_file:
            raise OSError("transient read error")
        return real_read_text(self, *a, **k)

    monkeypatch.setattr(env.Path, "read_text", _boom)

    env.fill_env_secrets()  # must not raise

    content = env_file.read_bytes().decode("utf-8")
    assert "already-set" not in content
    assert "POSTGRES_PASSWORD=" in content


# ── write_default_env ──────────────────────────────────────────────────────────


def test_write_default_env_fills_every_gen_placeholder(monkeypatch, tmp_path, capfd):
    env_file = tmp_path / ".env"
    monkeypatch.setattr(env, "ENV_FILE", env_file)

    env.write_default_env()

    content = env_file.read_text(encoding="utf-8")
    assert "<GEN:" not in content
    assert "POSTGRES_PASSWORD=" in content
    assert "legacy fallback" in capfd.readouterr().out.lower()


def test_write_default_env_generates_independent_secrets(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    monkeypatch.setattr(env, "ENV_FILE", env_file)

    env.write_default_env()

    content = env_file.read_text(encoding="utf-8")
    pg_pw = [
        ln.split("=", 1)[1]
        for ln in content.splitlines()
        if ln.startswith("POSTGRES_PASSWORD=")
    ][0]
    redis_pw = [
        ln.split("=", 1)[1]
        for ln in content.splitlines()
        if ln.startswith("REDIS_PASSWORD=")
    ][0]
    assert pg_pw != redis_pw
    assert len(pg_pw) == 64  # <GEN:32> -> 64 hex chars


# ── ensure_docker_gid ──────────────────────────────────────────────────────────


def test_ensure_docker_gid_noop_when_grp_module_unavailable(monkeypatch):
    monkeypatch.setitem(sys.modules, "grp", None)
    calls = []
    monkeypatch.setattr(env, "_upsert_env_key", lambda k, v: calls.append((k, v)))

    env.ensure_docker_gid()  # must not raise

    assert calls == []


def test_ensure_docker_gid_writes_when_gid_differs(monkeypatch):
    fake_grp = type(
        "grp",
        (),
        {"getgrnam": staticmethod(lambda name: type("G", (), {"gr_gid": 999})())},
    )
    monkeypatch.setitem(sys.modules, "grp", fake_grp)
    monkeypatch.setattr(env, "get", lambda key: "")
    calls = []
    monkeypatch.setattr(env, "_upsert_env_key", lambda k, v: calls.append((k, v)))

    env.ensure_docker_gid()

    assert calls == [("DOCKER_GID", "999")]


def test_ensure_docker_gid_noop_when_already_correct(monkeypatch):
    fake_grp = type(
        "grp",
        (),
        {"getgrnam": staticmethod(lambda name: type("G", (), {"gr_gid": 999})())},
    )
    monkeypatch.setitem(sys.modules, "grp", fake_grp)
    monkeypatch.setattr(env, "get", lambda key: "999")
    calls = []
    monkeypatch.setattr(env, "_upsert_env_key", lambda k, v: calls.append((k, v)))

    env.ensure_docker_gid()

    assert calls == []


def test_ensure_docker_gid_noop_when_group_missing(monkeypatch):
    fake_grp = type(
        "grp",
        (),
        {
            "getgrnam": staticmethod(
                lambda name: (_ for _ in ()).throw(KeyError("no such group"))
            )
        },
    )
    monkeypatch.setitem(sys.modules, "grp", fake_grp)
    calls = []
    monkeypatch.setattr(env, "_upsert_env_key", lambda k, v: calls.append((k, v)))

    env.ensure_docker_gid()  # must not raise

    assert calls == []


# ── prepare_env orchestration ──────────────────────────────────────────────────


@pytest.fixture
def _prepare_env_stubs(monkeypatch):
    calls = []
    for name in (
        "fill_env_secrets",
        "ensure_docker_gid",
        "sync_compose_env",
        "sync_telegraf_config",
        "ensure_bundles_state_file",
        "ensure_oidc_issuer_key",
        "render_authelia_config",
        "render_users_database",
    ):
        monkeypatch.setattr(env, name, lambda n=name: calls.append(n))
    monkeypatch.setattr(env, "_chmod_600", lambda path: calls.append("_chmod_600"))
    return calls


def test_prepare_env_creates_env_from_example_when_missing(
    monkeypatch, tmp_path, _prepare_env_stubs
):
    env_file = tmp_path / ".env"
    example = tmp_path / ".env.example"
    example.write_text("EXAMPLE=1\n", encoding="utf-8")
    monkeypatch.setattr(env, "ENV_FILE", env_file)
    monkeypatch.setattr(env, "ENV_EXAMPLE", example)

    env.prepare_env()

    assert env_file.read_text(encoding="utf-8") == "EXAMPLE=1\n"


def test_prepare_env_falls_back_to_write_default_env_when_no_example(
    monkeypatch, tmp_path, _prepare_env_stubs
):
    env_file = tmp_path / ".env"
    monkeypatch.setattr(env, "ENV_FILE", env_file)
    monkeypatch.setattr(env, "ENV_EXAMPLE", tmp_path / "missing.env.example")
    monkeypatch.setattr(
        env, "write_default_env", lambda: _prepare_env_stubs.append("write_default_env")
    )

    env.prepare_env()

    assert "write_default_env" in _prepare_env_stubs


def test_prepare_env_leaves_existing_env_untouched(
    monkeypatch, tmp_path, _prepare_env_stubs
):
    env_file = tmp_path / ".env"
    env_file.write_text("EXISTING=1\n", encoding="utf-8")
    monkeypatch.setattr(env, "ENV_FILE", env_file)
    monkeypatch.setattr(env, "ENV_EXAMPLE", tmp_path / "missing.env.example")

    env.prepare_env()

    assert env_file.read_text(encoding="utf-8") == "EXISTING=1\n"


def test_prepare_env_calls_every_step_in_order(
    monkeypatch, tmp_path, _prepare_env_stubs
):
    env_file = tmp_path / ".env"
    env_file.write_text("EXISTING=1\n", encoding="utf-8")
    monkeypatch.setattr(env, "ENV_FILE", env_file)
    monkeypatch.setattr(env, "ENV_EXAMPLE", tmp_path / "missing.env.example")

    env.prepare_env()

    assert _prepare_env_stubs == [
        "fill_env_secrets",
        "ensure_docker_gid",
        "_chmod_600",
        "sync_compose_env",
        "sync_telegraf_config",
        "ensure_bundles_state_file",
        "ensure_oidc_issuer_key",
        "render_authelia_config",
        "render_users_database",
    ]
