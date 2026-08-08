"""One-time fix for a Windows Docker Desktop credential-helper failure on hantal.

Symptom: `docker pull`/`docker build` (anything needing a registry touch) fails
with `error getting credentials - err: exit status 1, out: "A specified logon
session does not exist. It may already have been terminated."` -- confirmed
this happens even calling docker-credential-wincred.exe / docker-credential-
desktop.exe DIRECTLY (not just via the docker CLI), for BOTH the "default"
and "desktop-linux" contexts. Root cause: these are DPAPI/Windows-Credential-
Manager-backed helpers that need the interactive user's logon session: an
OpenSSH-for-Windows session runs sshd as a Windows SERVICE (Session 0),
which has no access to that session's credential vault -- a structural
limitation of driving this host over SSH, not a one-off misconfiguration.

Fix: give ~/.docker/config.json an explicit (empty) "auths" entry for Docker
Hub. When an explicit entry exists for a registry, the Docker CLI uses it
directly instead of shelling out to the credential helper for that registry
-- and public image pulls need no real credentials anyway, so an empty
`auth` value is sufficient. `credsStore` is also removed so nothing else
routes through the broken helper by default. Backs up the original config
first (config.json.bak-preclaude, only created once).

Usage (from a host that can reach hantal):
    python scripts/dev/remote_ssh.py hantal --raw --no-cd \
        "python C:\\path\\to\\hantal_fix_docker_creds.py"
Or copy this file to hantal first (see scripts/dev/README.md's transfer
pattern for files too large for a single SSH command line) and run it there
directly: `python hantal_fix_docker_creds.py`.
"""

import json
import os
import shutil

CONFIG_PATH = os.path.expandvars(r"%USERPROFILE%\.docker\config.json")
BACKUP_PATH = CONFIG_PATH + ".bak-preclaude"


def main() -> None:
    if not os.path.exists(BACKUP_PATH):
        shutil.copy2(CONFIG_PATH, BACKUP_PATH)
        print(f"backed up original config to {BACKUP_PATH}")

    with open(CONFIG_PATH) as f:
        cfg = json.load(f)

    cfg.pop("credsStore", None)
    cfg.setdefault("auths", {})
    cfg["auths"].setdefault("https://index.docker.io/v1/", {"auth": ""})

    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent="\t")

    print("patched config.json:", json.dumps(cfg, indent=2))


if __name__ == "__main__":
    main()
