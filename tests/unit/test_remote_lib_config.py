"""Unit tests for remote_lib's env loading, SOCKS5 proxy construction,
connect(), build_command(), and the known-hosts policy -- previously only
run()'s stdout-streaming path was covered (test_remote_lib_run.py). No real
SSH connection or subprocess is spawned: paramiko.SSHClient/ProxyCommand/
Ed25519Key are all stubbed.

`remote_lib` imports `paramiko` at module level -- a personal dev-workflow
dependency, deliberately not in src/requirements/*.txt, so CI's Unit Tests
job doesn't have it installed. Skip cleanly there instead of erroring, same
convention as test_remote_lib_run.py / test_remote_ssh_arg_parsing.py.
"""

import pytest

pytest.importorskip("paramiko")

import paramiko  # noqa: E402

from scripts.dev import remote_lib  # noqa: E402

# ── load_env / _require ───────────────────────────────────────────────────────


def test_load_env_exits_when_file_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(remote_lib, "ENV_PATH", tmp_path / "does-not-exist.env")
    with pytest.raises(SystemExit):
        remote_lib.load_env()


def test_load_env_parses_skips_comments_blanks_and_malformed_lines(
    monkeypatch, tmp_path
):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# a comment\n"
        "\n"
        "HANTAL_HOST=100.123.71.54\n"
        'HANTAL_USER="someone@example.com"\n'
        "HANTAL_DIR='C:\\repo'\n"
        "not-a-valid-line-no-equals\n"
        "  PI_HOST = 10.0.0.5  \n"
    )
    monkeypatch.setattr(remote_lib, "ENV_PATH", env_file)

    env = remote_lib.load_env()

    assert env["HANTAL_HOST"] == "100.123.71.54"
    assert env["HANTAL_USER"] == "someone@example.com"
    assert env["HANTAL_DIR"] == "C:\\repo"
    assert "not-a-valid-line-no-equals" not in env
    assert env["PI_HOST"] == "10.0.0.5"


def test_require_returns_value_when_present():
    assert remote_lib._require({"KEY": "value"}, "KEY") == "value"


def test_require_exits_when_key_missing():
    with pytest.raises(SystemExit):
        remote_lib._require({}, "KEY")


def test_require_exits_when_value_empty():
    with pytest.raises(SystemExit):
        remote_lib._require({"KEY": ""}, "KEY")


# ── _proxy_sock ────────────────────────────────────────────────────────────────


def test_proxy_sock_returns_none_when_unset():
    assert remote_lib._proxy_sock({}, "HANTAL", "100.123.71.54") is None


def test_proxy_sock_returns_none_when_blank():
    env = {"HANTAL_SOCKS5": "   "}
    assert remote_lib._proxy_sock(env, "HANTAL", "100.123.71.54") is None


def test_proxy_sock_builds_socks5_proxycommand_when_set(monkeypatch):
    captured = {}

    def _fake_proxy_command(cmd):
        captured["cmd"] = cmd
        return "the-proxy-command"

    monkeypatch.setattr(remote_lib.paramiko, "ProxyCommand", _fake_proxy_command)
    env = {"HANTAL_SOCKS5": "localhost:1055"}

    result = remote_lib._proxy_sock(env, "HANTAL", "100.123.71.54")

    assert result == "the-proxy-command"
    assert captured["cmd"] == (
        "socat - SOCKS5:localhost:100.123.71.54:22,socksport=1055"
    )


# ── build_command ──────────────────────────────────────────────────────────────

_HANTAL_CFG = {"prefix": "HANTAL", "chain": ";", "shell": "powershell"}
_PI_CFG = {"prefix": "PI", "chain": "&&", "shell": "raw"}


def test_build_command_joins_with_chain_operator_raw_host():
    cmd = remote_lib.build_command(
        _PI_CFG, {"PI_DIR": ""}, ["echo one", "echo two"], no_cd=True, raw=False
    )
    assert cmd == "echo one && echo two"


def test_build_command_prefixes_cd_when_workdir_set():
    cmd = remote_lib.build_command(
        _PI_CFG, {"PI_DIR": "/opt/minder"}, ["git pull"], no_cd=False, raw=True
    )
    assert cmd == "cd /opt/minder && git pull"


def test_build_command_skips_cd_when_no_cd_true():
    cmd = remote_lib.build_command(
        _PI_CFG, {"PI_DIR": "/opt/minder"}, ["git pull"], no_cd=True, raw=True
    )
    assert cmd == "git pull"


def test_build_command_skips_cd_when_command_already_starts_with_cd():
    cmd = remote_lib.build_command(
        _PI_CFG,
        {"PI_DIR": "/opt/minder"},
        ["cd /somewhere-else && ls"],
        no_cd=False,
        raw=True,
    )
    assert cmd == "cd /somewhere-else && ls"


def test_build_command_skips_cd_when_workdir_unset():
    cmd = remote_lib.build_command(_PI_CFG, {}, ["git pull"], no_cd=False, raw=True)
    assert cmd == "git pull"


def test_build_command_windows_uses_semicolon_and_single_quoted_cd():
    cmd = remote_lib.build_command(
        _HANTAL_CFG,
        {"HANTAL_DIR": "E:\\Projects\\minder"},
        ["git pull"],
        no_cd=False,
        raw=True,
    )
    assert cmd == "cd 'E:\\Projects\\minder'; git pull"


def test_build_command_wraps_in_powershell_unless_raw():
    cmd = remote_lib.build_command(
        _HANTAL_CFG, {}, ["Get-Process"], no_cd=True, raw=False
    )
    assert cmd == 'powershell -NoProfile -Command "Get-Process"'


def test_build_command_raw_flag_skips_powershell_wrapping():
    cmd = remote_lib.build_command(
        _HANTAL_CFG, {}, ["Get-Process"], no_cd=True, raw=True
    )
    assert cmd == "Get-Process"


def test_build_command_escapes_embedded_double_quotes_in_powershell_wrap():
    cmd = remote_lib.build_command(
        _HANTAL_CFG, {}, ['Write-Output "hi"'], no_cd=True, raw=False
    )
    assert cmd == 'powershell -NoProfile -Command "Write-Output \\"hi\\""'


# ── _KnownHostsPolicy ────────────────────────────────────────────────────────


def test_known_hosts_policy_accepts_a_verified_key():
    policy = remote_lib._KnownHostsPolicy()
    fake_client = type(
        "C",
        (),
        {
            "get_host_keys": lambda self: type(
                "K", (), {"check": lambda self, h, k: True}
            )()
        },
    )()
    policy.missing_host_key(fake_client, "hantal", "fake-key")  # must not raise


def test_known_hosts_policy_rejects_an_unverified_key():
    policy = remote_lib._KnownHostsPolicy()
    fake_client = type(
        "C",
        (),
        {
            "get_host_keys": lambda self: type(
                "K", (), {"check": lambda self, h, k: False}
            )()
        },
    )()
    with pytest.raises(paramiko.SSHException):
        policy.missing_host_key(fake_client, "hantal", "fake-key")


# ── connect ────────────────────────────────────────────────────────────────────


class _FakeSSHClient:
    instances = []

    def __init__(self):
        self.calls = []
        self.connect_kwargs = None
        _FakeSSHClient.instances.append(self)

    def load_system_host_keys(self):
        self.calls.append("load_system_host_keys")

    def set_missing_host_key_policy(self, policy):
        self.calls.append(("set_missing_host_key_policy", type(policy).__name__))

    def connect(self, host, **kwargs):
        self.calls.append(("connect", host))
        self.connect_kwargs = kwargs


@pytest.fixture(autouse=True)
def _fake_ssh_client(monkeypatch):
    _FakeSSHClient.instances = []
    monkeypatch.setattr(remote_lib.paramiko, "SSHClient", _FakeSSHClient)


def test_connect_unknown_alias_exits():
    with pytest.raises(SystemExit):
        remote_lib.connect("not-a-real-host")


def test_connect_key_auth_loads_ed25519_key_and_connects(monkeypatch, tmp_path):
    key_file = tmp_path / "hantal_key"
    key_file.write_text("not a real key")
    monkeypatch.setattr(
        remote_lib,
        "load_env",
        lambda: {
            "HANTAL_HOST": "100.123.71.54",
            "HANTAL_USER": "someone",
            "HANTAL_KEY": str(key_file),
        },
    )
    monkeypatch.setattr(
        remote_lib.paramiko.Ed25519Key,
        "from_private_key_file",
        staticmethod(lambda path: f"key-loaded-from-{path}"),
    )

    client, cfg, env = remote_lib.connect("hantal")

    assert cfg is remote_lib.HOSTS["hantal"]
    assert client.connect_kwargs["username"] == "someone"
    assert client.connect_kwargs["pkey"] == f"key-loaded-from-{key_file}"
    assert client.connect_kwargs["sock"] is None
    assert ("connect", "100.123.71.54") in client.calls


def test_connect_password_auth(monkeypatch):
    monkeypatch.setattr(
        remote_lib,
        "load_env",
        lambda: {
            "PI_HOST": "192.168.1.50",
            "PI_USER": "pi",
            "PI_PASSWORD": "raspberry",
        },
    )

    client, cfg, env = remote_lib.connect("pi")

    assert client.connect_kwargs["username"] == "pi"
    assert client.connect_kwargs["password"] == "raspberry"
    assert "pkey" not in client.connect_kwargs


def test_connect_uses_the_socks5_proxy_sock_when_configured(monkeypatch):
    monkeypatch.setattr(
        remote_lib,
        "load_env",
        lambda: {
            "PI_HOST": "192.168.1.50",
            "PI_USER": "pi",
            "PI_PASSWORD": "raspberry",
            "PI_SOCKS5": "localhost:1055",
        },
    )
    monkeypatch.setattr(
        remote_lib.paramiko, "ProxyCommand", lambda cmd: f"proxy({cmd})"
    )

    client, cfg, env = remote_lib.connect("pi")

    assert (
        client.connect_kwargs["sock"]
        == "proxy(socat - SOCKS5:localhost:192.168.1.50:22,socksport=1055)"
    )


def test_connect_missing_required_key_exits(monkeypatch):
    monkeypatch.setattr(remote_lib, "load_env", lambda: {"PI_HOST": "192.168.1.50"})
    with pytest.raises(SystemExit):
        remote_lib.connect("pi")
