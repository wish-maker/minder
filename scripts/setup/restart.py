"""`restart` verb — ported from scripts/lib/commands.sh cmd_restart (#7, Stage 2).

Just stop, pause, start — both halves are ported + verified verbs.
"""

import time

from . import start, stop


def run() -> int:
    stop.run()
    time.sleep(3)
    return start.run()
