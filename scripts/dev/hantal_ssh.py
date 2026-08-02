"""SSH runner for the Windows dev box ("hantal") — thin CLI wrapper around
remote_lib.py's shared connect/run core (alias "hantal" in HOSTS there). Kept
as a dedicated entrypoint for muscle memory / existing docs; `remote_ssh.py
hantal ...` does the same thing.

hantal runs a full local Docker stack (see its own `.claude/CLAUDE.md`) and is
reached over Tailscale. Two things make it different from the Pi:

  1. Auth is SSH key-based (OpenSSH Server on Windows), not password.
  2. From a dev host that has no direct route onto the tailnet (e.g. a sandboxed
     container with no /dev/net/tun, so tailscaled runs in
     `--tun=userspace-networking` mode), reaching hantal's tailnet IP requires
     going through tailscaled's own SOCKS5 proxy. Set HANTAL_SOCKS5 to
     `host:port` (default when tailscaled is started with
     `--socks5-server=localhost:1055`) and this routes through `socat` as the
     ProxyCommand. Leave HANTAL_SOCKS5 unset when running from a host that's
     already a normal tailnet peer (e.g. from hantal itself, or another box
     with a real `tailscale0` interface).

Secrets/config live in a **gitignored** `scripts/dev/.env` (shared with
pi_ssh.py — never committed). Copy `scripts/dev/.env.example` to
`scripts/dev/.env` and fill in the HANTAL_* keys.

Usage:
    python scripts/dev/hantal_ssh.py '<remote command>'
    python scripts/dev/hantal_ssh.py '<cmd1>' '<cmd2>'      # chained with ;
    python scripts/dev/hantal_ssh.py --no-cd '<command run from user home>'
    python scripts/dev/hantal_ssh.py --raw 'whoami'   # skip the powershell wrapper

Commands are run through `powershell -NoProfile -Command` by default (Windows'
default SSH shell is cmd.exe, which most dev commands here don't target) unless
--raw is passed. When HANTAL_DIR is set (and --no-cd isn't passed), the command
is prefixed with `cd '<dir>';` so it runs from the repo checkout.
"""

import sys

import remote_lib


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    argv = sys.argv[1:]
    no_cd = raw = False
    while argv and argv[0] in ("--no-cd", "--raw"):
        if argv[0] == "--no-cd":
            no_cd = True
        else:
            raw = True
        argv = argv[1:]
    cmds = argv if argv else ["echo no-cmd"]
    return remote_lib.run("hantal", cmds, no_cd=no_cd, raw=raw)


if __name__ == "__main__":
    sys.exit(main())
