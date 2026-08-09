#!/usr/bin/env python3
"""Upload a local file to a configured remote dev host via SFTP.

The base64-inline-through-a-shell-command trick used elsewhere in this
directory hits a hard argument-length limit on Windows/PowerShell ("The
command line is too long.") for anything more than a few KB. SFTP has no such
limit and is the right tool whenever a real file transfer (not a small
config patch) is needed.

Usage:
    python scripts/dev/remote_put.py <alias> <local_path> <remote_path>

<remote_path> is relative to the host's configured working directory
(<PREFIX>_DIR in .env) unless it's absolute.
"""

import sys
from pathlib import Path

import remote_lib


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    alias, local_path, remote_path = sys.argv[1:4]

    client, cfg, env = remote_lib.connect(alias)
    try:
        prefix = cfg["prefix"]
        workdir = env.get(f"{prefix}_DIR", "")
        if workdir and not Path(remote_path).is_absolute():
            sep = "\\" if cfg["shell"] == "powershell" else "/"
            remote_path = f"{workdir.rstrip('/\\')}{sep}{remote_path}"

        sftp = client.open_sftp()
        try:
            sftp.put(local_path, remote_path)
        finally:
            sftp.close()
        print(f"Uploaded {local_path} -> {alias}:{remote_path}")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
