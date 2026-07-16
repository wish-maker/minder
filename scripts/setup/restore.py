"""`restore` verb — ported from scripts/lib/commands.sh cmd_restore (#7, Stage 2).

`restore [archive]` — restore .env + PostgreSQL + Qdrant + RabbitMQ definitions
from a `backups/minder-<ts>.tar.gz` produced by `backup`. With no argument it
lists the available archives (interactive pick), else it errors non-interactively.

FIDELITY — the dry-run seam:
  cmd_restore's actual restore operations are BARE `docker`/`cp` calls (NOT
  `run`-wrapped), so — unlike most verbs — they are NOT dry-run-gated: they
  execute for real even under DRY_RUN, and overwrite live data. Only `compose up
  -d postgres` (the auto-start when postgres is down) goes through the gated
  `compose`. This port reproduces that exactly (bare calls → un-gated
  subprocess). DRY_RUN therefore does NOT make `restore <valid-archive>` safe —
  a bash wart carried over faithfully (candidate for an issue), which is why the
  gate (scripts/gate/restore_verify.sh) only drives the NON-DESTRUCTIVE early
  exits — no-backups / no-archive-arg / file-not-found — and the real restore is
  exercised by hand against a throwaway stack.

KNOWN BASH QUIRK (carried over): the Qdrant restore copies `qdrant.tar.gz` into
the container's `/tmp/` but then extracts `/tmp/qdrant-backup.tar.gz` — a filename
mismatch vs what it just copied. Preserved verbatim (fixing it would be a behavior
change, not a port); worth a follow-up issue.
"""

import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from . import backup, config, docker, log


def _restore_postgres(sql_file: Path) -> bool:
    """bash `docker exec -i <pg> psql -U minder -f - < file &>/dev/null 2>&1`:
    feed the dump on stdin, discard all output; True on exit 0. Bare (un-gated)."""
    try:
        with open(sql_file, "rb") as fh:
            return subprocess.run(
                ["docker", "exec", "-i", docker.container_name("postgres"),
                 "psql", "-U", "minder", "-f", "-"],
                stdin=fh, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            ).returncode == 0
    except OSError:
        return False


def _run_bare(argv: list[str], *, stderr_null: bool = False) -> int:
    """A bare `docker …` call (NOT `run`-wrapped → un-gated, runs even under
    DRY_RUN). `stderr_null` mirrors a trailing `2>/dev/null`. 127 if docker missing."""
    try:
        return subprocess.run(
            argv, stderr=subprocess.DEVNULL if stderr_null else None
        ).returncode
    except OSError:
        return 127


def _select_archive() -> "str | None":
    """The no-argument path: list `backups/minder-*.tar.gz` newest-first, then pick
    (interactive) or error (non-interactive). Returns the chosen archive path, or
    None when the caller should stop with exit 1 (already logged)."""
    color = log._colors_on()
    b = log._BOLD if color else ""
    c = log._CYAN if color else ""
    d = log._DIM if color else ""
    nc = log._NC if color else ""

    # echo -e "\n${BOLD}Available backups:${NC}"
    log._emit("")
    log._emit(f"{b}Available backups:{nc}")

    files = sorted(config.BACKUP_DIR.glob("minder-*.tar.gz"), reverse=True)
    for i, f in enumerate(files, 1):
        size = backup._du_sh(f)
        # basename "$f" .tar.gz | sed 's/minder-//'
        ts = f.name[: -len(".tar.gz")].replace("minder-", "", 1)
        log._emit(f"  {c}[{i}]{nc}  {ts}  {d}{size}{nc}")

    if not files:
        log.error(f"No backups found in {config.BACKUP_DIR}")
        return None

    if config.INTERACTIVE:
        sys.stdout.write(f"\nSelect backup [1-{len(files)}]: ")
        sys.stdout.flush()
        choice = sys.stdin.readline().rstrip("\n")
        try:
            return str(files[int(choice) - 1])
        except (ValueError, IndexError):
            # bash: an out-of-range/non-numeric index yields an empty archive, which
            # then fails the `[[ ! -f ]]` check below → "File not found: ".
            return ""

    log.error(
        f"No backup archive specified. Usage: ./{config.SCRIPT_NAME} "
        "restore <archive.tar.gz>"
    )
    return None


def run(archive: str = "") -> int:
    if not archive:
        selected = _select_archive()
        if selected is None:
            return 1
        archive = selected

    if not Path(archive).is_file():
        log.error(f"File not found: {archive}")
        return 1

    log.section(f"♻️   Restore  ←  {Path(archive).name}")
    log.warn("This will OVERWRITE current data. Services must be stopped.")

    if config.INTERACTIVE:
        sys.stdout.write("Continue? [y/N] ")
        sys.stdout.flush()
        if sys.stdin.readline().rstrip("\n").lower() != "y":
            log.info("Restore cancelled.")
            return 0

    tmp_dir = Path(tempfile.mkdtemp())
    log.spinner_start("Extracting archive…")
    try:
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(tmp_dir, filter="data")
    except (OSError, tarfile.TarError):
        pass  # bash's `tar xzf` is unguarded too; a bad archive leaves restore_dir empty
    log.spinner_stop()
    subdirs = sorted(p for p in tmp_dir.iterdir() if p.is_dir())
    restore_dir = subdirs[0] if subdirs else None

    # ── .env (bare cp — un-gated) ─────────────────────────────────────────
    if restore_dir and (restore_dir / "env.backup").is_file():
        shutil.copy(restore_dir / "env.backup", config.ENV_FILE)
        try:
            config.ENV_FILE.chmod(0o600)
        except OSError:
            pass
        log.success(".env restored")

    # ── ensure postgres is up (compose up is dry-run-gated) ───────────────
    if not docker.container_running("postgres"):
        docker.compose("up", "-d", "postgres")
        docker.wait_postgres_ready()

    # ── PostgreSQL (bare psql on stdin — un-gated) ────────────────────────
    if restore_dir and (restore_dir / "postgres.sql").is_file():
        log.spinner_start("Restoring PostgreSQL…")
        ok = _restore_postgres(restore_dir / "postgres.sql")
        log.spinner_stop()
        if ok:
            log.success("PostgreSQL restored")
        else:
            log.warn("PostgreSQL restore had errors (partial restore possible)")

    # ── Qdrant (bare cp + exec — un-gated; filename-mismatch quirk preserved) ─
    if restore_dir and (restore_dir / "qdrant.tar.gz").is_file() and docker.container_running("qdrant"):
        log.spinner_start("Restoring Qdrant…")
        qname = docker.container_name("qdrant")
        _run_bare(["docker", "cp", str(restore_dir / "qdrant.tar.gz"), f"{qname}:/tmp/"])
        _run_bare(
            ["docker", "exec", qname, "tar", "xzf", "/tmp/qdrant-backup.tar.gz", "-C", "/"],
            stderr_null=True,
        )
        log.spinner_stop()
        log.success("Qdrant restored")

    # ── RabbitMQ definitions (bare cp + exec — un-gated) ──────────────────
    if restore_dir and (restore_dir / "rabbitmq-definitions.json").is_file() and docker.container_running("rabbitmq"):
        log.spinner_start("Restoring RabbitMQ definitions…")
        rname = docker.container_name("rabbitmq")
        _run_bare(["docker", "cp", str(restore_dir / "rabbitmq-definitions.json"),
                   f"{rname}:/tmp/rabbitmq-defs.json"])
        ok = _run_bare(
            ["docker", "exec", rname, "rabbitmqctl", "import_definitions",
             "/tmp/rabbitmq-defs.json"],
            stderr_null=True,
        ) == 0
        log.spinner_stop()
        if ok:
            log.success("RabbitMQ definitions restored")
        else:
            log.warn("RabbitMQ definitions restore had errors")

    shutil.rmtree(tmp_dir, ignore_errors=True)
    log.success(f"Restore complete — restart services: ./{config.SCRIPT_NAME} start")
    return 0
