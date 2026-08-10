"""Shared core for the `*_ssh.py` / `remote_ssh.py` dev-host runners: one place
for env loading, SOCKS5 proxying, and command execution, so adding a new host
is a HOSTS entry plus its `<PREFIX>_*` keys in `scripts/dev/.env` — not a new
paramiko re-implementation.

See `scripts/dev/README.md` for usage and `docs/development/tailscale-bridge.md`
for why the SOCKS5 proxy exists at all.
"""

import sys
from pathlib import Path

import paramiko


class _KnownHostsPolicy(paramiko.MissingHostKeyPolicy):
    """Reject any host key not already in the user's known_hosts -- but check via
    HostKeys.check() (hash-aware), not paramiko.RejectPolicy directly. SSHClient.connect()
    looks up `self._system_host_keys.get(hostname)` (a PLAIN dict lookup) before ever
    calling this policy; when known_hosts was written with OpenSSH's default
    HashKnownHosts=yes (hostnames stored as `|1|salt|hash`, as on this box), that lookup
    always misses even for an already-trusted host, so THIS policy runs for every
    connection regardless. HostKeys.check() correctly hashes `hostname` and compares,
    so a genuinely-known host (confirmed via `ssh` at least once) still succeeds; only a
    truly unrecognized or changed key is rejected.
    """

    def missing_host_key(self, client, hostname, key):
        if client.get_host_keys().check(hostname, key):
            return
        raise paramiko.SSHException(
            f"host key for {hostname!r} not found in known_hosts (or the key "
            "changed) -- run `ssh` to it manually once to verify and trust it"
        )


ENV_PATH = Path(__file__).with_name(".env")

# alias -> config used by connect()/build_command().
#   prefix: env var prefix, e.g. "PI" reads PI_HOST/PI_USER/...
#   auth:   "password" (<PREFIX>_PASSWORD) or "key" (<PREFIX>_KEY, Ed25519)
#   shell:  "raw" (native remote shell, e.g. bash) or "powershell" (wrapped in
#           `powershell -NoProfile -Command "..."` unless --raw is passed)
#   chain:  operator used to prefix `cd <dir>` and to join multiple commands
#           passed on one invocation ("&&" for bash hosts, ";" for Windows).
#           Assumes the host's *wrapped* shell (e.g. powershell) — passing
#           --raw together with multiple commands bypasses that wrapper, so
#           the operator must then match the raw remote shell instead (e.g.
#           hantal's raw shell is cmd.exe, which wants "&" instead of ";").
#   get_pty: force a PTY (needed for boxes whose console glyphs need one)
HOSTS = {
    "pi": {
        "prefix": "PI",
        "auth": "password",
        "shell": "raw",
        "chain": "&&",
        "get_pty": True,
    },
    "hantal": {
        "prefix": "HANTAL",
        "auth": "key",
        "shell": "powershell",
        "chain": ";",
        "get_pty": False,
    },
}


# Reusable, no-argument command sequences for `remote_ssh.py <alias> --job
# <name>` — keyed by shell (not alias), so the same job works on any host of
# that shell type. Every host drives its own checkout through scripts/setup/
# (see repo README) rather than raw `docker compose`, which needs the -f
# docker/docker-compose.yml + profile flags scripts/setup/docker.py already
# pins — a bare `docker compose ...` here would silently target the wrong
# project. `setup.sh` itself needs bash, so hosts without it (Windows) call
# `python -m scripts.setup` directly instead — same underlying Python module.
JOBS = {
    "update": {
        "raw": ["git pull", "bash setup.sh update"],
        "powershell": ["git pull", "python -m scripts.setup update"],
    },
    "restart": {
        "raw": ["bash setup.sh restart"],
        "powershell": ["python -m scripts.setup restart"],
    },
    "status": {
        "raw": ["bash setup.sh status"],
        "powershell": ["python -m scripts.setup status"],
    },
    "prune-images": {
        # Dangling images only (same command scripts/setup/stop.py's --clean
        # runs) — NOT `setup.sh stop --clean`, which tears the whole stack down
        # first; this is meant as a standalone maintenance job.
        "raw": ["docker image prune -f"],
        "powershell": ["docker image prune -f"],
    },
    # tests/unit only, with the same dummy creds CI's unit-tests job sets (see
    # .github/workflows/ci.yml) — unit tests mock their DB/Redis access rather
    # than hitting the host's real running stack, so this is safe to run
    # against a live box. Deliberately excludes tests/integration + tests/e2e:
    # CI spins those up their own disposable Postgres/Redis containers, which
    # a live box doesn't have — running them here would either fail outright
    # or, worse, hit the box's real data-bearing services.
    "test": {
        "raw": [
            "POSTGRES_HOST=localhost POSTGRES_PORT=5432 POSTGRES_USER=postgres "
            "POSTGRES_PASSWORD=test_password POSTGRES_DB=minder_test "
            # DB_* mirrors POSTGRES_* (#265): services on MinderBaseSettings (now
            # including rag-pipeline/tts-stt/marketplace/plugin-state-manager,
            # #313) read DB_HOST/PORT/USER/PASSWORD/NAME, not the legacy
            # POSTGRES_* names — missing these fails Settings() at import time,
            # aborting test collection entirely (not just a test failure).
            "DB_HOST=localhost DB_PORT=5432 DB_USER=postgres "
            "DB_PASSWORD=test_password DB_NAME=minder_test "
            "REDIS_HOST=localhost REDIS_PORT=6379 REDIS_PASSWORD=test_password "
            "JWT_SECRET=test_jwt_secret_for_ci NEO4J_AUTH=neo4j/test_password "
            "python3 -m pytest tests/unit/ -v --tb=short"
        ],
        "powershell": [
            "$env:POSTGRES_HOST='localhost'; $env:POSTGRES_PORT='5432'; "
            "$env:POSTGRES_USER='postgres'; $env:POSTGRES_PASSWORD='test_password'; "
            "$env:POSTGRES_DB='minder_test'; "
            "$env:DB_HOST='localhost'; $env:DB_PORT='5432'; "
            "$env:DB_USER='postgres'; $env:DB_PASSWORD='test_password'; "
            "$env:DB_NAME='minder_test'; "
            "$env:REDIS_HOST='localhost'; "
            "$env:REDIS_PORT='6379'; $env:REDIS_PASSWORD='test_password'; "
            "$env:JWT_SECRET='test_jwt_secret_for_ci'; "
            "$env:NEO4J_AUTH='neo4j/test_password'; "
            "python -m pytest tests/unit/ -v --tb=short"
        ],
    },
}


def load_env() -> dict:
    if not ENV_PATH.exists():
        sys.exit(
            f"missing {ENV_PATH} — copy scripts/dev/.env.example to it and fill in "
            "the connection keys (the file is gitignored)."
        )
    env = {}
    for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def _require(env: dict, key: str):
    if key not in env or not env[key]:
        sys.exit(f"{ENV_PATH} is missing required key {key} (see .env.example)")
    return env[key]


def _proxy_sock(env: dict, prefix: str, host: str):
    """tailscaled's userspace-networking SOCKS5 proxy, via socat, when this dev
    host has no direct tailnet route (no real tailscale0 interface). Unset
    <PREFIX>_SOCKS5 when running from a normal tailnet peer — direct TCP is
    used instead."""
    socks5 = env.get(f"{prefix}_SOCKS5", "").strip()
    if not socks5:
        return None
    sock_host, _, sock_port = socks5.partition(":")
    return paramiko.ProxyCommand(
        f"socat - SOCKS5:{sock_host}:{host}:22,socksport={sock_port}"
    )


def connect(alias: str):
    """Return a connected paramiko SSHClient for `alias`, plus its HOSTS config
    and the loaded env (both needed by build_command)."""
    if alias not in HOSTS:
        sys.exit(f"unknown host alias {alias!r} — choices: {', '.join(HOSTS)}")
    cfg = HOSTS[alias]
    prefix = cfg["prefix"]
    env = load_env()
    host = _require(env, f"{prefix}_HOST")
    user = _require(env, f"{prefix}_USER")
    sock = _proxy_sock(env, prefix, host)

    client = paramiko.SSHClient()
    # Load the user's own known_hosts so a host key they've already verified (e.g. via
    # a manual `ssh`) is checked against, then REJECT anything not in there.
    # AutoAddPolicy silently accepted ANY key with no record kept (not even TOFU -- it
    # doesn't persist accepted keys), so neither a spoofed host nor a legitimately
    # rotated key was ever distinguishable. WarningPolicy (tried first) still connects
    # to an unknown/changed key, only logging -- CodeQL correctly flags that as unsafe
    # too. paramiko.RejectPolicy itself doesn't work here (see _KnownHostsPolicy) since
    # this box's known_hosts is hashed; _KnownHostsPolicy does the same reject, correctly.
    # Requires `ssh pi`/`ssh hantal` to have been run manually at least once (populating
    # the real ~/.ssh/known_hosts) before this tool works -- the correct tradeoff: a
    # changed/spoofed key now hard-fails instead of quietly connecting.
    client.load_system_host_keys()
    client.set_missing_host_key_policy(_KnownHostsPolicy())
    if cfg["auth"] == "key":
        key_path = _require(env, f"{prefix}_KEY")
        key = paramiko.Ed25519Key.from_private_key_file(
            str(Path(key_path).expanduser())
        )
        client.connect(host, username=user, pkey=key, sock=sock, timeout=30)
    else:
        password = _require(env, f"{prefix}_PASSWORD")
        client.connect(host, username=user, password=password, sock=sock, timeout=30)
    return client, cfg, env


def build_command(cfg: dict, env: dict, cmds: list, no_cd: bool, raw: bool) -> str:
    """Join `cmds` with the host's chain operator, prefix `cd <dir>` unless
    no_cd (or the first command already starts with `cd `), and wrap in
    powershell unless raw or the host's shell is already native."""
    prefix = cfg["prefix"]
    cmd = f" {cfg['chain']} ".join(cmds)
    workdir = env.get(f"{prefix}_DIR", "")
    if workdir and not no_cd and not cmd.lstrip().startswith("cd "):
        if cfg["shell"] == "powershell":
            cmd = f"cd '{workdir}'; {cmd}"
        else:
            cmd = f"cd {workdir} && {cmd}"
    if cfg["shell"] == "powershell" and not raw:
        escaped = cmd.replace('"', '\\"')
        cmd = f'powershell -NoProfile -Command "{escaped}"'
    return cmd


def run(
    alias: str, cmds: list, no_cd: bool = False, raw: bool = False, no_pty: bool = False
) -> int:
    """Connect to `alias`, run `cmds` (chained per HOSTS[alias]), stream output,
    and return the remote exit status. `no_pty` overrides HOSTS[alias]'s default
    to force no PTY for this call — needed for CLIs whose interactive-terminal
    UI (e.g. openclaw's @clack/prompts-style rendering) hangs waiting for an
    ANSI cursor-position response that a bare PTY with no real terminal emulator
    driving it never sends (confirmed 2026-08-02: `openclaw agents add` hung
    indefinitely over a PTY channel, completed in ~30s with none)."""
    client, cfg, env = connect(alias)
    cmd = build_command(cfg, env, cmds, no_cd, raw)
    get_pty = False if no_pty else cfg.get("get_pty", False)
    try:
        _, stdout, stderr = client.exec_command(cmd, timeout=1800, get_pty=get_pty)
        # ChannelFile.readline() in text mode decodes with strict utf-8 (paramiko's
        # `u()` helper, no errors= knob) -- a remote PowerShell command whose output
        # contains a Windows-1252 byte (e.g. a curly quote, 0x94/0x93/0x92 from
        # PowerShell's own formatting or an error message) crashes this loop with
        # UnicodeDecodeError and kills the whole SSH call. Read the same channel via
        # a binary makefile instead and decode ourselves with errors="replace".
        raw_stdout = stdout.channel.makefile("rb")
        for line in iter(raw_stdout.readline, b""):
            sys.stdout.write(line.decode("utf-8", "replace"))
            sys.stdout.flush()
        rc = stdout.channel.recv_exit_status()
        tail = stderr.read().decode("utf-8", "replace")
        if tail.strip():
            sys.stdout.write(tail)
        return rc
    finally:
        client.close()
