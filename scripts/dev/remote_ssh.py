"""Generic parametric CLI over remote_lib.py — run one or more commands on any
configured host (see HOSTS in remote_lib.py) without writing a new script.
Sibling to (and shared implementation behind) `pi_ssh.py` / `hantal_ssh.py`.

Usage:
    python scripts/dev/remote_ssh.py --list
    python scripts/dev/remote_ssh.py --list-jobs
    python scripts/dev/remote_ssh.py <alias> '<cmd>'
    python scripts/dev/remote_ssh.py <alias> '<cmd1>' '<cmd2>' '<cmd3>'
    python scripts/dev/remote_ssh.py <alias> --no-cd '<cmd run from user home>'
    python scripts/dev/remote_ssh.py <alias> --raw '<cmd>'   # skip shell wrapping (e.g. powershell)
    python scripts/dev/remote_ssh.py <alias> --job <name>    # e.g. update, restart, status, prune-images

Multiple positional commands run as one remote invocation, chained with the
host's operator (&& for bash hosts, ; for the Windows/powershell host) — for a
recurring multi-step job (pull, rebuild, healthcheck), pass each step as its
own argument instead of hand-joining a string each time. `--job <name>` runs
one of the fixed, no-argument sequences in remote_lib.JOBS instead (same name
works on any host — the job resolves to that host's shell).

Add a new host by adding an entry to HOSTS in remote_lib.py and its
`<PREFIX>_*` keys to scripts/dev/.env — no new script file needed. Add a new
job by adding an entry to JOBS in remote_lib.py, keyed by shell.
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

    if argv and argv[0] == "--list-jobs":
        for name in remote_lib.JOBS:
            print(name)
        return 0

    if not argv:
        sys.exit(
            "usage: remote_ssh.py <alias> [--no-cd] [--raw] '<cmd>' ['<cmd2>' ...]\n"
            "       remote_ssh.py <alias> --job <name>\n"
            "       remote_ssh.py --list | --list-jobs"
        )

    alias, argv = argv[0], argv[1:]
    if alias not in remote_lib.HOSTS:
        sys.exit(f"unknown host alias {alias!r} — choices: {', '.join(remote_lib.HOSTS)}")
    cfg = remote_lib.HOSTS[alias]

    if argv and argv[0] == "--job":
        if len(argv) < 2:
            sys.exit("--job needs a name — see: remote_ssh.py --list-jobs")
        job_name = argv[1]
        job = remote_lib.JOBS.get(job_name)
        if job is None:
            sys.exit(f"unknown job {job_name!r} — choices: {', '.join(remote_lib.JOBS)}")
        cmds = job.get(cfg["shell"])
        if cmds is None:
            sys.exit(f"job {job_name!r} has no {cfg['shell']} variant for host {alias!r}")
        return remote_lib.run(alias, cmds)

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
