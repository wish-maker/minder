# scripts/dev/ — developer-only tooling

Helpers used while developing/validating Minder that are **not** part of the setup
CLI (`scripts/setup/`), the parity gate (`scripts/gate/`), or the bash reference
lib (`scripts/lib/`). Nothing here is imported by the platform at runtime.

## `remote_ssh.py` + `remote_lib.py` — drive any configured dev host

`remote_lib.py` is the shared core (env loading, SOCKS5 proxying, command
chaining/execution) behind every host runner below — it holds a `HOSTS` dict
keyed by alias (currently `pi`, `hantal`). `remote_ssh.py` is a generic CLI
over it, so a new host is a `HOSTS` entry + its `<PREFIX>_*` keys in `.env`,
not a new script:

```bash
python scripts/dev/remote_ssh.py --list                       # configured aliases
python scripts/dev/remote_ssh.py pi 'git log --oneline -1'
python scripts/dev/remote_ssh.py hantal 'git log -1' 'docker ps --format "{{.Names}}"'  # chained
python scripts/dev/remote_ssh.py hantal --raw --no-cd 'whoami'
```

Multiple positional commands run as one remote invocation, chained with the
host's operator (`&&` for bash hosts, `;` for the Windows/powershell host) —
useful for a recurring multi-step job (pull, rebuild, healthcheck) without
hand-joining a shell string each time.

`pi_ssh.py` and `hantal_ssh.py` (below) are thin, alias-bound wrappers over the
same `remote_lib.run()` — kept for muscle memory / existing docs.

### `--job <name>` — fixed no-argument sequences

For the operations you actually run over and over (pull + rebuild, restart,
check status, clear old images), `remote_lib.JOBS` holds one command sequence
per shell type — the same job name works on any host, resolved to that host's
shell:

```bash
python scripts/dev/remote_ssh.py --list-jobs         # update, restart, status, prune-images, test
python scripts/dev/remote_ssh.py hantal --job status
python scripts/dev/remote_ssh.py pi --job update      # git pull && bash setup.sh update
python scripts/dev/remote_ssh.py hantal --job update  # git pull ; python -m scripts.setup update
python scripts/dev/remote_ssh.py pi --job test        # tests/unit only, CI's dummy creds
```

Jobs shell out to `scripts/setup/` (`setup.sh` on bash hosts, `python -m
scripts.setup` where bash may not exist, e.g. Windows) rather than raw `docker
compose`, since the compose file lives at `docker/docker-compose.yml` and needs
the `-f`/profile flags `scripts/setup/docker.py` already pins. `prune-images`
is the exception — it's a standalone `docker image prune -f` (dangling images
only), deliberately **not** `setup.sh stop --clean`, which tears the whole
stack down first.

`update`/`restart`/`prune-images` mutate a live stack — only `status` (read-only)
has been exercised against both real hosts; run the others once by hand before
scripting them into anything unattended. `test` runs only `tests/unit/` (mocked
DB/Redis, same dummy creds CI's unit-tests job uses) — deliberately not
`tests/integration`/`tests/e2e`, which in CI get their own disposable Postgres/
Redis containers that a live box doesn't have.

Add a job by adding an entry to `JOBS` in `remote_lib.py`, keyed by shell
(`"raw"` or `"powershell"`) — no CLI changes needed.

## `pi_ssh.py` — drive the RPi-4 validation box

Minder is validated on real ARM hardware (a Raspberry Pi 4).

```bash
# one-time: create the gitignored secrets file
cp scripts/dev/.env.example scripts/dev/.env   # then edit with the box's creds

# run a command on the Pi (runs from $PI_DIR by default)
python scripts/dev/pi_ssh.py 'git log --oneline -1'
python scripts/dev/pi_ssh.py 'docker ps --format "{{.Names}} {{.Status}}"'
python scripts/dev/pi_ssh.py --no-cd 'uname -a'
```

`scripts/dev/.env` holds the address + credentials and is **gitignored** (the repo
root `.gitignore` `.env` rule covers it). Never commit it. `.env.example` is the
committed template documenting the required keys.

Same as `hantal_ssh.py` below, if this dev host has no direct tailnet route, set
`PI_SOCKS5=host:port` in `.env` to route through tailscaled's SOCKS5 proxy.

## `hantal_ssh.py` — drive the Windows dev box

A second dev machine ("hantal") runs its own full local Docker stack (see its
own `.claude/CLAUDE.md` there) and is reached over Tailscale. Same idea as
`pi_ssh.py`, but SSH-key auth instead of password, and commands run through
`powershell` by default since Windows' SSH default shell is `cmd.exe`.

```bash
# one-time: same gitignored .env as pi_ssh.py, extended with HANTAL_* keys
cp scripts/dev/.env.example scripts/dev/.env   # then fill in HANTAL_HOST/USER/KEY/DIR

python scripts/dev/hantal_ssh.py 'git log -1 --oneline'
python scripts/dev/hantal_ssh.py 'docker ps --format "{{.Names}}"'
python scripts/dev/hantal_ssh.py --raw --no-cd 'whoami'   # skip cd + powershell wrapping
```

`hantal_fix_docker_creds.py`: one-time fix for `docker pull`/`build` failing over
SSH with `error getting credentials - err: exit status 1, out: "A specified
logon session does not exist."` — Windows Credential Manager-backed helpers
(`wincred`/`docker-credential-desktop`) need the interactive desktop session,
which an OpenSSH-for-Windows session (Session 0) can't reach. Copy it to hantal
and run it there (`python hantal_fix_docker_creds.py`) to give
`~/.docker/config.json` an explicit empty auth entry for Docker Hub, skipping
the broken helper for anonymous pulls. Only needed once per hantal setup (or
after Docker Desktop resets its config) — already applied as of 2026-08-08.

`pi_reap_orphaned_pagers.sh`: kills orphaned PTY `pager` processes on the Pi
(git's own pager, left running forever when its owning session died without
cleanup — see the openclaw-rpi-context memory for the full incident, 32 of
them drove load average to 33 on the Pi's 4 cores on 2026-08-08). Safe by
design — only targets a process named `pager` whose parent is *also* orphaned
(PPid 1) and has run 5+ minutes. Already folded into `/opt/openclaw-scripts/
cleanup.sh`'s daily cron on the Pi itself (self-healing going forward); this
copy is for running it by hand or on a different host if the same pattern
shows up there — transfer + run it the same base64 way as
`hantal_fix_docker_creds.py` above (`--dry-run` first to see what it would
kill without touching anything).

`scheduled-backup.ps1`: daily backup wrapper for hantal — runs `python -m
scripts.setup backup` and logs the result to `logs/scheduled-backup.log`.
Exists because hantal had NO scheduled backup at all (confirmed live
2026-08-19: the newest backup on disk was 15 days stale) despite
`scripts/setup/backup.py` itself working fine the whole time — nothing was
ever wired up to call it on a schedule. Register once:
```
schtasks /Create /TN "MinderDailyBackup" /SC DAILY /ST 03:00 /F /TR ^
  "powershell -NoProfile -ExecutionPolicy Bypass -File <repo>\scripts\dev\scheduled-backup.ps1"
```
Known limitation: without `/RU`+`/RP` this registers as "Interactive only" —
it won't fire if the user isn't logged into an active session at 03:00. See
the script's own header comment for why that's the accepted tradeoff here.

If the dev host running this script has no direct tailnet route (a sandboxed
container with no `/dev/net/tun`, so `tailscaled` runs in
`--tun=userspace-networking` mode), set `HANTAL_SOCKS5=host:port` in `.env` to
route through tailscaled's own SOCKS5 proxy (needs `socat` installed:
`apt-get install -y socat`). Leave it blank when running from a real tailnet
peer. `tailscale_bootstrap.sh` automates standing up exactly that proxy from a
fresh sandbox (installs `tailscale`+`socat`, brings up userspace-networking,
wires the SOCKS5 listener) — idempotent, run as root:

```bash
bash scripts/dev/tailscale_bootstrap.sh
```

See `docs/development/tailscale-bridge.md` for the full explanation of why
this is needed and what the script does step by step.

## `remote_put.py` — transfer a real file to a dev host

The base64-inline-through-a-shell-command trick the other scripts use for small
config patches hits a hard argument-length limit on Windows/PowerShell ("The
command line is too long.") for anything more than a few KB. Use this instead
for a real file transfer — it goes over SFTP, no size limit:

```bash
python scripts/dev/remote_put.py <alias> <local_path> <remote_path>
```

`<remote_path>` is relative to the host's configured working directory
(`<PREFIX>_DIR` in `.env`) unless it's absolute.

## `dev.py` — collapse the repetitive PR-loop commands

Wraps the command sequences the PR flow runs over and over into one call each, so a
green local run predicts a green CI run and the CI-poll no longer needs a hand-run
sleep+grep loop.

```bash
python scripts/dev/dev.py ci <PR>            # one-shot CI verdict (ALL GREEN / FAILING / pending)
python scripts/dev/dev.py ci <PR> --watch    # poll until every check is terminal, then verdict
python scripts/dev/dev.py lint <path>...     # black --check + isort --check-only + flake8 (CI flags)
python scripts/dev/dev.py mypy <service>     # per-service mypy with the repo pyproject config
python scripts/dev/dev.py test [pytest args] # unit tests (tests/unit by default)
```

- `ci --watch` is the big token/time saver — safe to run in the background; it prints
  the verdict once CI finishes (and returns early with exit 1 if a check fails).
- `lint`/`mypy` mirror `.github/workflows/quality.yml` exactly (flake8 `--max-line-length=120
  --extend-ignore=E203,W503`; mypy per-service dir as its own import root). Note the CI
  lint/mypy scope is `src/services|shared|scripts|tests` — `src/plugins/` is **not** gated,
  so `lint` those paths manually before pushing plugin changes.
- Exit codes: `0` = clean/green, `1` = lint/mypy/test failure or CI failing, `2` = CI pending.
