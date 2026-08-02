"""Generic parametric CLI over remote_lib.py — run one or more commands on any
configured host (see HOSTS in remote_lib.py) without writing a new script.
Sibling to (and shared implementation behind) `pi_ssh.py` / `hantal_ssh.py`.

Usage:
    python scripts/dev/remote_ssh.py --list
    python scripts/dev/remote_ssh.py <alias> '<cmd>'
    python scripts/dev/remote_ssh.py <alias> '<cmd1>' '<cmd2>' '<cmd3>'
    python scripts/dev/remote_ssh.py <alias> --no-cd '<cmd run from user home>'
    python scripts/dev/remote_ssh.py <alias> --raw '<cmd>'   # skip shell wrapping (e.g. powershell)

Multiple positional commands run as one remote invocation, chained with the
host's operator (&& for bash hosts, ; for the Windows/powershell host) — for a
recurring multi-step job (pull, rebuild, healthcheck), pass each step as its
own argument instead of hand-joining a string each time.

Add a new host by adding an entry to HOSTS in remote_lib.py and its
`<PREFIX>_*` keys to scripts/dev/.env — no new script file needed.
"""

import sys

import remote_lib


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    argv = sys.argv[1:]

    if argv and argv[0] in ("--list", "-l"):
        for alias in remote_lib.HOSTS:
            print(alias)
        return 0

    if not argv:
        sys.exit(
            "usage: remote_ssh.py <alias> [--no-cd] [--raw] '<cmd>' ['<cmd2>' ...]\n"
            "       remote_ssh.py --list"
        )

    alias, argv = argv[0], argv[1:]
    no_cd = raw = False
    while argv and argv[0] in ("--no-cd", "--raw"):
        if argv[0] == "--no-cd":
            no_cd = True
        else:
            raw = True
        argv = argv[1:]

    cmds = argv if argv else ["echo no-cmd"]
    return remote_lib.run(alias, cmds, no_cd=no_cd, raw=raw)


if __name__ == "__main__":
    sys.exit(main())
