"""`restore` verb — ported from scripts/lib/commands.sh cmd_restore (#7, Stage 2).

`restore [archive]` — restore .env + PostgreSQL + Qdrant + RabbitMQ definitions
from a `backups/minder-<ts>.tar.gz` produced by `backup`. With no argument it
lists the available archives (interactive pick), else it errors non-interactively.

DRY_RUN (#55, fixed): the restore steps MUTATE live data, so they are now gated —
docker steps via docker.run() (echo-only under DRY_RUN), and the .env copy /
psql / rabbitmq steps behind an explicit `config.DRY_RUN` branch (the seam can't
carry their stdin redirect / result check). The archive extraction is read-only
(temp dir) so it always runs, keeping a dry-run preview informative. So
`DRY_RUN=1 restore <archive>` now PREVIEWS rather than overwrites — which is what
lets scripts/gate/restore_verify.sh exercise the full restore path, not just the
non-destructive early exits.

Qdrant (#56, fixed): copy in AND extract the same `/tmp/qdrant.tar.gz`. The bash
original copied `qdrant.tar.gz` into the container but extracted a stale/absent
`/tmp/qdrant-backup.tar.gz`, so the Qdrant restore silently did nothing.
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
    """A bare `docker …` call whose RESULT is checked (so it can't go through the
    echo-only seam) — only invoked on the real (non-DRY_RUN) path. `stderr_null`
    mirrors a trailing `2>/dev/null`. 127 if docker is missing."""
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

    # ── .env (native copy; DRY_RUN echoes the cp/chmod like bash's `run`) ──
    if restore_dir and (restore_dir / "env.backup").is_file():
        if config.DRY_RUN:
            docker.run("cp", str(restore_dir / "env.backup"), str(config.ENV_FILE))
            docker.run("chmod", "600", str(config.ENV_FILE))
        else:
            shutil.copy(restore_dir / "env.backup", config.ENV_FILE)
            try:
                config.ENV_FILE.chmod(0o600)
            except OSError:
                pass
        log.success(".env restored")

    # ── ensure postgres is up (compose up gated; wait skipped under DRY_RUN) ─
    if not docker.container_running("postgres"):
        docker.compose("up", "-d", "postgres")
        if not config.DRY_RUN:
            docker.wait_postgres_ready()

    # ── PostgreSQL ─────────────────────────────────────────────────────────
    if restore_dir and (restore_dir / "postgres.sql").is_file():
        log.spinner_start("Restoring PostgreSQL…")
        pgname = docker.container_name("postgres")
        if config.DRY_RUN:
            docker.run("docker", "exec", "-i", pgname, "psql", "-U", "minder", "-f", "-")
            ok = True
        else:
            ok = _restore_postgres(restore_dir / "postgres.sql")
        log.spinner_stop()
        if ok:
            log.success("PostgreSQL restored")
        else:
            log.warn("PostgreSQL restore had errors (partial restore possible)")

    # ── Qdrant (#56: copy in AND extract the same /tmp/qdrant.tar.gz) ──────
    if restore_dir and (restore_dir / "qdrant.tar.gz").is_file() and docker.container_running("qdrant"):
        log.spinner_start("Restoring Qdrant…")
        qname = docker.container_name("qdrant")
        docker.run("docker", "cp", str(restore_dir / "qdrant.tar.gz"), f"{qname}:/tmp/qdrant.tar.gz")
        docker.run("docker", "exec", qname, "tar", "xzf", "/tmp/qdrant.tar.gz", "-C", "/")
        log.spinner_stop()
        log.success("Qdrant restored")

    # ── RabbitMQ definitions ──────────────────────────────────────────────
    if restore_dir and (restore_dir / "rabbitmq-definitions.json").is_file() and docker.container_running("rabbitmq"):
        log.spinner_start("Restoring RabbitMQ definitions…")
        rname = docker.container_name("rabbitmq")
        docker.run("docker", "cp", str(restore_dir / "rabbitmq-definitions.json"),
                   f"{rname}:/tmp/rabbitmq-defs.json")
        if config.DRY_RUN:
            docker.run("docker", "exec", rname, "rabbitmqctl", "import_definitions",
                       "/tmp/rabbitmq-defs.json")
            ok = True
        else:
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
