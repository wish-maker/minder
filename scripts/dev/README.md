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
