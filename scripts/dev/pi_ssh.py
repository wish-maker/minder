"""SSH runner for the RPi-4 validation box — the standing way to drive the Pi from
a dev host (the platform is validated on real ARM hardware; see the pi-arm
validation notes).

Secrets live in a **gitignored** `scripts/dev/.env` (never committed — the repo's
root `.gitignore` `.env` rule already covers it). Copy `scripts/dev/.env.example`
to `scripts/dev/.env` and fill in the box's address/credentials.

Usage:
    python scripts/dev/pi_ssh.py '<remote command>'
    python scripts/dev/pi_ssh.py --no-cd '<command run from $HOME>'

When PI_DIR is set (and the command doesn't already start with `cd `), the command
is run from that directory — so `pi_ssh.py 'git log -1'` runs inside the project.
Password auth is used because the box only offers that; stdout is forced to UTF-8
so the ✓/⚠ glyphs don't crash a cp1254 Windows console. Long jobs should be
`setsid … </dev/null >log 2>&1 &` on the remote so they survive the channel close.
"""

import sys
from pathlib import Path

import paramiko

ENV_PATH = Path(__file__).with_name(".env")


def _load_env() -> dict:
    if not ENV_PATH.exists():
        sys.exit(
            f"missing {ENV_PATH} — copy scripts/dev/.env.example to it and fill in "
            "the Pi address/credentials (the file is gitignored)."
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
    if argv and argv[0] == "--no-cd":
        no_cd, argv = True, argv[1:]
    cmd = argv[0] if argv else "echo no-cmd"

    env = _load_env()
    try:
        host = env["PI_HOST"]
        user = env["PI_USER"]
        password = env["PI_PASSWORD"]
    except KeyError as e:
        sys.exit(f"{ENV_PATH} is missing required key {e} (see .env.example)")
    workdir = env.get("PI_DIR", "")

    if workdir and not no_cd and not cmd.lstrip().startswith("cd "):
        cmd = f"cd {workdir} && {cmd}"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=user, password=password, timeout=30)
    _, stdout, stderr = client.exec_command(cmd, timeout=1800, get_pty=True)
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
