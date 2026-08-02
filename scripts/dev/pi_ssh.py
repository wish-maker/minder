"""SSH runner for the RPi-4 validation box — thin CLI wrapper around
remote_lib.py's shared connect/run core (alias "pi" in HOSTS there). Kept as a
dedicated entrypoint for muscle memory / existing docs; `remote_ssh.py pi ...`
does the same thing.

Secrets live in a **gitignored** `scripts/dev/.env` (never committed — the repo's
root `.gitignore` `.env` rule already covers it). Copy `scripts/dev/.env.example`
to `scripts/dev/.env` and fill in the box's address/credentials.

Usage:
    python scripts/dev/pi_ssh.py '<remote command>'
    python scripts/dev/pi_ssh.py '<cmd1>' '<cmd2>'          # chained with &&
    python scripts/dev/pi_ssh.py --no-cd '<cmd run from $HOME>'

When PI_DIR is set (and the command doesn't already start with `cd `), the command
is run from that directory — so `pi_ssh.py 'git log -1'` runs inside the project.
Password auth is used because the box only offers that; stdout is forced to UTF-8
so the ✓/⚠ glyphs don't crash a cp1254 Windows console. Long jobs should be
`setsid … </dev/null >log 2>&1 &` on the remote so they survive the channel close.

From a dev host with no direct tailnet route (e.g. a sandboxed container with no
/dev/net/tun, so tailscaled runs in `--tun=userspace-networking` mode), set
PI_SOCKS5 to `host:port` (same tailscaled proxy used by hantal_ssh.py, default
localhost:1055) to route through it via `socat`. Leave PI_SOCKS5 unset when
running from a host that's already a normal tailnet peer.
"""

import sys

import remote_lib


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    argv = sys.argv[1:]
    no_cd = False
    if argv and argv[0] == "--no-cd":
        no_cd, argv = True, argv[1:]
    cmds = argv if argv else ["echo no-cmd"]
    return remote_lib.run("pi", cmds, no_cd=no_cd)


if __name__ == "__main__":
    sys.exit(main())
