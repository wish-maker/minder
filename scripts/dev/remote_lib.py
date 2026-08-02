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
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if cfg["auth"] == "key":
        key_path = _require(env, f"{prefix}_KEY")
        key = paramiko.Ed25519Key.from_private_key_file(str(Path(key_path).expanduser()))
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


def run(alias: str, cmds: list, no_cd: bool = False, raw: bool = False) -> int:
    """Connect to `alias`, run `cmds` (chained per HOSTS[alias]), stream output,
    and return the remote exit status."""
    client, cfg, env = connect(alias)
    cmd = build_command(cfg, env, cmds, no_cd, raw)
    try:
        _, stdout, stderr = client.exec_command(
            cmd, timeout=1800, get_pty=cfg.get("get_pty", False)
        )
        for line in iter(stdout.readline, ""):
            sys.stdout.write(line)
            sys.stdout.flush()
        rc = stdout.channel.recv_exit_status()
        tail = stderr.read().decode("utf-8", "replace")
        if tail.strip():
            sys.stdout.write(tail)
        return rc
    finally:
        client.close()
