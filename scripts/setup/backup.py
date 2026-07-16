"""`backup` verb — ported from scripts/lib/commands.sh cmd_backup (#7, Stage 2).

Full platform backup into `backups/minder-<ts>.tar.gz`: .env + PostgreSQL dump +
Neo4j dump + InfluxDB backup + Qdrant snapshot + RabbitMQ definitions, then a
gzip archive and a keep-last-7 prune. Faithful to the bash original, including
WHICH steps go through the dry-run seam and which do not:

  un-gated (run for real even under DRY_RUN, exactly like bash):
    mkdir dest · cp .env → env.backup · the PostgreSQL `pg_dumpall` (a bare
    `docker exec … > file`, NOT wrapped in run) · the final `tar` archive + the
    keep-last-7 prune.
  dry-run-gated (docker.run → echoes under DRY_RUN):
    Neo4j dump, InfluxDB backup+cp, Qdrant snapshot+cp, RabbitMQ export+cp.

Everything writes only into `backups/` (+ ephemeral container `/tmp`); the platform
data is never mutated — a backup is read-only w.r.t. the live stack. Verified under
DRY_RUN=1 against the live stack via scripts/gate/backup_verify.sh (the un-gated
`pg_dumpall`/`tar` really run — matching bash — so the verify cleans up `backups/`).
"""

import datetime
import shutil
import subprocess
import tarfile
from pathlib import Path

from . import config, docker, env, log


def _human_size(nbytes: int) -> str:
    """Human-readable size in `du -h` style (1024-based, one decimal, unit letter).
    Cosmetic only — it annotates a log line and is normalized away by the gate; a
    Python formatter is used instead of shelling out to `du` to stay cross-OS, so
    the block-rounding may differ from bash's `du -sh` (never the structure)."""
    size = float(nbytes)
    for unit in ("", "K", "M", "G", "T", "P"):
        if size < 1024.0:
            return str(int(size)) if unit == "" else f"{size:.1f}{unit}"
        size /= 1024.0
    return f"{size:.1f}E"


def _du_sh(path: Path) -> str:
    """Mirror `du -sh <path> | cut -f1`: a size string, or "" when the path is
    missing (bash: `du` errors to stderr, `cut` of empty stdout → "")."""
    try:
        return _human_size(path.stat().st_size)
    except OSError:
        return ""


def _dump_to_file(argv: list[str], dest_file: Path) -> bool:
    """bash `<cmd> 2>/dev/null > file` (the un-gated PostgreSQL dump): execute with
    stdout → file, stderr discarded; True on exit 0. NOT dry-run-gated — bash runs
    this directly (no `run` wrapper), so it dumps for real even under DRY_RUN."""
    try:
        with open(dest_file, "wb") as fh:
            return (
                subprocess.run(argv, stdout=fh, stderr=subprocess.DEVNULL).returncode
                == 0
            )
    except OSError:
        return False


def _run_to_file(argv: list[str], dest_file: Path) -> bool:
    """bash `run <cmd> 2>/dev/null > file` (the Neo4j dump): dry-run-gated exactly
    like docker.run(), but with stdout redirected to a file instead of the console.
    Under DRY_RUN, run()'s `[dry-run] …` echo is what the caller's `> file` captures
    (so it lands in the file, not on the console) and the call "succeeds" (exit 0);
    under real mode the command streams its output to the file, stderr discarded."""
    if config.DRY_RUN:
        # run() joins args with newlines (setup.sh's IFS=$'\n\t'); mirror docker.run.
        line = "[dry-run] " + "\n".join(argv)
        text = f"{log._DIM}{line}{log._NC}" if log._colors_on() else line
        try:
            dest_file.write_text(text + "\n", encoding="utf-8")
        except OSError:
            return False
        return True
    try:
        with open(dest_file, "wb") as fh:
            return (
                subprocess.run(argv, stdout=fh, stderr=subprocess.DEVNULL).returncode
                == 0
            )
    except OSError:
        return False


def _make_archive(archive: Path, base_dir: Path, name: str) -> bool:
    """bash `tar czf "$archive" -C "$BACKUP_DIR" "minder-<ts>"` — NOT dry-run-gated
    (runs for real). Python `tarfile` (cross-OS) instead of shelling out to `tar`;
    the archive contents match, the exact bytes/size do not (gzip mtime etc.), which
    is cosmetic and normalized away by the gate."""
    try:
        with tarfile.open(archive, "w:gz") as tf:
            tf.add(base_dir / name, arcname=name)
        return True
    except (OSError, tarfile.TarError):
        return False


def run() -> int:
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = config.BACKUP_DIR / f"minder-{ts}"
    dest.mkdir(parents=True, exist_ok=True)

    log.section(f"💾  Platform Backup  →  {dest}")

    # ── .env ──────────────────────────────────────────────────────────────
    if config.ENV_FILE.is_file():
        shutil.copy(config.ENV_FILE, dest / "env.backup")
        try:
            (dest / "env.backup").chmod(0o600)
        except OSError:
            pass
        log.success(".env backed up")
    else:
        log.warn(".env not found")

    # ── PostgreSQL (un-gated bare docker exec + redirect) ─────────────────
    if docker.container_running("postgres"):
        log.spinner_start("Dumping PostgreSQL…")
        dump = dest / "postgres.sql"
        ok = _dump_to_file(
            [
                "docker",
                "exec",
                docker.container_name("postgres"),
                "pg_dumpall",
                "-U",
                "minder",
            ],
            dump,
        )
        log.spinner_stop()
        if ok:
            log.success(f"PostgreSQL  ({_du_sh(dump)})")
        else:
            log.warn("PostgreSQL dump failed")
    else:
        log.warn("PostgreSQL not running — skipped")

    # ── Neo4j (dry-run-gated run + redirect) ──────────────────────────────
    if docker.container_running("neo4j"):
        log.spinner_start("Dumping Neo4j…")
        neo4j_dump = dest / "neo4j.dump"
        ok = _run_to_file(
            [
                "docker",
                "exec",
                docker.container_name("neo4j"),
                "neo4j-admin",
                "database",
                "dump",
                "neo4j",
                "--to-stdout",
            ],
            neo4j_dump,
        )
        log.spinner_stop()
        if ok:
            log.success(f"Neo4j  ({_du_sh(neo4j_dump)})")
        else:
            log.warn("Neo4j dump failed")
    else:
        log.warn("Neo4j not running — skipped")

    # ── InfluxDB (dry-run-gated; exec quiet like bash's `&>/dev/null`) ────
    if docker.container_running("influxdb"):
        log.spinner_start("Backing up InfluxDB…")
        influx_token = env.get("INFLUXDB_ADMIN_TOKEN")
        if influx_token:
            iname = docker.container_name("influxdb")
            # bash: `run docker exec … influx backup … &>/dev/null` → run()'s echo is
            # sent to /dev/null (quiet=True), so only the following `run docker cp`
            # (un-quiet) prints its [dry-run] line to the console.
            if (
                docker.run(
                    "docker",
                    "exec",
                    iname,
                    "influx",
                    "backup",
                    "/tmp/influx-backup",
                    "--token",
                    influx_token,
                    quiet=True,
                )
                == 0
            ):
                docker.run(
                    "docker", "cp", f"{iname}:/tmp/influx-backup", f"{dest}/influxdb/"
                )
                log.spinner_stop()
                log.success("InfluxDB backed up")
            else:
                log.spinner_stop()
                log.warn("InfluxDB backup failed")
        else:
            log.spinner_stop()
            log.warn("INFLUXDB_ADMIN_TOKEN not set — skipping InfluxDB backup")
    else:
        log.warn("InfluxDB not running — skipped")

    # ── Qdrant (dry-run-gated snapshot + cp) ──────────────────────────────
    if docker.container_running("qdrant"):
        log.spinner_start("Snapshotting Qdrant storage…")
        qname = docker.container_name("qdrant")
        qdrant_tar = dest / "qdrant.tar.gz"
        if (
            docker.run(
                "docker",
                "exec",
                qname,
                "tar",
                "czf",
                "/tmp/qdrant-backup.tar.gz",
                "/qdrant/storage",
            )
            == 0
            and docker.run(
                "docker",
                "cp",
                f"{qname}:/tmp/qdrant-backup.tar.gz",
                f"{dest}/qdrant.tar.gz",
            )
            == 0
        ):
            log.spinner_stop()
            log.success(f"Qdrant  ({_du_sh(qdrant_tar)})")
        else:
            log.spinner_stop()
            log.warn("Qdrant snapshot failed")
    else:
        log.warn("Qdrant not running — skipped")

    # ── RabbitMQ (dry-run-gated export + cp) ──────────────────────────────
    if docker.container_running("rabbitmq"):
        log.spinner_start("Backing up RabbitMQ definitions…")
        rname = docker.container_name("rabbitmq")
        if (
            docker.run(
                "docker",
                "exec",
                rname,
                "rabbitmqctl",
                "export_definitions",
                "/tmp/rabbitmq-defs.json",
            )
            == 0
            and docker.run(
                "docker",
                "cp",
                f"{rname}:/tmp/rabbitmq-defs.json",
                f"{dest}/rabbitmq-definitions.json",
            )
            == 0
        ):
            log.spinner_stop()
            log.success("RabbitMQ definitions backed up")
        else:
            log.spinner_stop()
            log.warn("RabbitMQ definitions export failed")
    else:
        log.warn("RabbitMQ not running — skipped")

    # ── Compress (un-gated) ───────────────────────────────────────────────
    log.spinner_start("Compressing backup archive…")
    archive = config.BACKUP_DIR / f"minder-{ts}.tar.gz"
    if _make_archive(archive, config.BACKUP_DIR, f"minder-{ts}"):
        shutil.rmtree(dest, ignore_errors=True)
        log.spinner_stop()
        log.success(f"Archive: {archive}  ({_du_sh(archive)})")
    else:
        log.spinner_stop()
        log.warn(f"Compression failed — uncompressed backup kept at {dest}")

    # ── Prune (keep last 7, un-gated) ─────────────────────────────────────
    archives = sorted(config.BACKUP_DIR.glob("minder-*.tar.gz"))
    if len(archives) > 7:
        for old in archives[: len(archives) - 7]:
            try:
                old.unlink()
            except OSError:
                pass
        log.detail("Pruned old backups (keeping last 7)")

    log.success("Backup complete")
    return 0
