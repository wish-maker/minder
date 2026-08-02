"""SSH runner for the Windows dev box ("hantal") — the standing way to drive it
from a dev host without re-deriving the connection each session, sibling to
`pi_ssh.py`.

hantal runs a full local Docker stack (see its own `.claude/CLAUDE.md`) and is
reached over Tailscale. Two things make it different from the Pi:

  1. Auth is SSH key-based (OpenSSH Server on Windows), not password.
  2. From a dev host that has no direct route onto the tailnet (e.g. a sandboxed
     container with no /dev/net/tun, so tailscaled runs in
     `--tun=userspace-networking` mode), reaching hantal's tailnet IP requires
     going through tailscaled's own SOCKS5 proxy. Set HANTAL_SOCKS5 to
     `host:port` (default when tailscaled is started with
     `--socks5-server=localhost:1055`) and this script shells out to `socat`
     as the ProxyCommand. Leave HANTAL_SOCKS5 unset when running from a host
     that's already a normal tailnet peer (e.g. from hantal itself, or another
     box with a real `tailscale0` interface) — direct TCP is used instead.

Secrets/config live in a **gitignored** `scripts/dev/.env` (shared with
pi_ssh.py — never committed). Copy `scripts/dev/.env.example` to
`scripts/dev/.env` and fill in the HANTAL_* keys.

Usage:
    python scripts/dev/hantal_ssh.py '<remote command>'
    python scripts/dev/hantal_ssh.py --no-cd '<command run from user home>'
    python scripts/dev/hantal_ssh.py --raw 'whoami'   # skip the powershell wrapper

Commands are run through `powershell -NoProfile -Command` by default (Windows'
default SSH shell is cmd.exe, which most dev commands here don't target) unless
--raw is passed. When HANTAL_DIR is set (and --no-cd isn't passed), the command
is prefixed with `cd '<dir>';` so it runs from the repo checkout.
"""

import sys
from pathlib import Path

import paramiko

ENV_PATH = Path(__file__).with_name(".env")


def _load_env() -> dict:
    if not ENV_PATH.exists():
        sys.exit(
            f"missing {ENV_PATH} — copy scripts/dev/.env.example to it and fill in "
            "the HANTAL_* keys (the file is gitignored)."
        )
    env: dict = {}
    for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    argv = sys.argv[1:]
    no_cd = False
    raw = False
    while argv and argv[0] in ("--no-cd", "--raw"):
        if argv[0] == "--no-cd":
            no_cd = True
        else:
            raw = True
        argv = argv[1:]
    cmd = argv[0] if argv else "echo no-cmd"

    env = _load_env()
    try:
        host = env["HANTAL_HOST"]
        user = env["HANTAL_USER"]
        key_path = env["HANTAL_KEY"]
    except KeyError as e:
        sys.exit(f"{ENV_PATH} is missing required key {e} (see .env.example)")
    workdir = env.get("HANTAL_DIR", "")
    socks5 = env.get("HANTAL_SOCKS5", "").strip()

    if workdir and not no_cd:
        cmd = f"cd '{workdir}'; {cmd}"
    if not raw:
        escaped = cmd.replace('"', '\\"')
        cmd = f'powershell -NoProfile -Command "{escaped}"'

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    key = paramiko.Ed25519Key.from_private_key_file(str(Path(key_path).expanduser()))

    sock = None
    if socks5:
        # tailscaled's userspace-networking SOCKS5 proxy — needed only when this
        # host has no direct tailnet route (no tailscale0 interface).
        sock_host, _, sock_port = socks5.partition(":")
        sock = paramiko.ProxyCommand(
            f"socat - SOCKS5:{sock_host}:{host}:{22},socksport={sock_port}"
        )

    client.connect(host, username=user, pkey=key, sock=sock, timeout=30)
    _, stdout, stderr = client.exec_command(cmd, timeout=1800)
    for line in iter(stdout.readline, ""):
        sys.stdout.write(line)
        sys.stdout.flush()
    rc = stdout.channel.recv_exit_status()
    tail = stderr.read().decode("utf-8", "replace")
    if tail.strip():
        sys.stdout.write(tail)
    client.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
