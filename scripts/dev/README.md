# scripts/dev/ — developer-only tooling

Helpers used while developing/validating Minder that are **not** part of the setup
CLI (`scripts/setup/`), the parity gate (`scripts/gate/`), or the bash reference
lib (`scripts/lib/`). Nothing here is imported by the platform at runtime.

## `pi_ssh.py` — drive the RPi-4 validation box

Minder is validated on real ARM hardware (a Raspberry Pi 4). This is a small
paramiko SSH runner so that workflow doesn't have to be re-typed each session.

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
