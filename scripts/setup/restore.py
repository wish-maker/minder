"""`restore` verb — ported from scripts/lib/commands.sh cmd_restore (#7, Stage 2).

`restore [archive]` — restore .env + PostgreSQL + Neo4j + InfluxDB + Qdrant +
RabbitMQ definitions from a `backups/minder-<ts>.tar.gz` produced by `backup`.
With no argument it
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

#281/#282/#283 (fixed): PostgreSQL restore now uses `-v ON_ERROR_STOP=1` so a
restore onto an already-initialized DB actually surfaces as a failure instead of
reporting success while silently not overwriting data; a corrupt/truncated
archive (extracts to no subdirectory) now errors out instead of falling through
to "Restore complete" having restored nothing; and every per-store step now
tracks into a `skipped` list (container not running, or the restore itself
failed) that is surfaced in the final summary line — mirroring backup.py's own
`skipped` list for the same "silent partial success" failure mode (#177).
"""

import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from . import backup, config, docker, infra, log


def _restore_postgres(sql_file: Path) -> bool:
    """bash `docker exec -i <pg> psql -U minder -d postgres -v ON_ERROR_STOP=1
    -f - < file &>/dev/null 2>&1`: feed the dump on stdin, discard all output;
    True on exit 0. Bare (un-gated).

    -d postgres (found live, 2026-08-04, while verifying #281 on hantal): psql
    with no -d connects to a database NAMED AFTER THE USER — here "minder", the
    very database the dump's `--clean` DROPs and recreates. `DROP DATABASE
    minder` while connected TO minder always fails ("cannot drop the currently
    open database"), regardless of ON_ERROR_STOP — a pre-existing bug, just
    invisible before #281 added ON_ERROR_STOP (psql printed the error and kept
    going). `postgres` is pg_dumpall's own maintenance DB, deliberately excluded
    from the dump's DROP list, so connecting there lets the restore drop/recreate
    every real database including "minder" itself.

    -v ON_ERROR_STOP=1 (#281): without it, psql keeps going past SQL errors and
    still exits 0 — so restoring an old backup (dumped without --clean
    --if-exists, #281's other half) onto an already-initialized Postgres would
    error on every CREATE DATABASE/CREATE TABLE as "already exists", yet still
    report "PostgreSQL restored". With ON_ERROR_STOP, a real error now actually
    surfaces as a non-zero exit → the caller's existing warn branch fires
    instead of a false success."""
    try:
        with open(sql_file, "rb") as fh:
            return (
                subprocess.run(
                    [
                        "docker",
                        "exec",
                        "-i",
                        docker.container_name("postgres"),
                        "psql",
                        "-U",
                        "minder",
                        "-d",
                        "postgres",
                        "-v",
                        "ON_ERROR_STOP=1",
                        "-f",
                        "-",
                    ],
                    stdin=fh,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                ).returncode
                == 0
            )
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
    else:
        log.warn("NONINTERACTIVE — skipping confirmation, proceeding")

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

    # #283: a corrupt/truncated archive extracts to nothing (or extractall raised
    # and was swallowed above, matching bash) — every restore step below is gated
    # on `restore_dir and ...`, so without this check the run would silently
    # restore NOTHING and still fall through to "Restore complete" at the bottom.
    if restore_dir is None:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        log.error(
            f"'{Path(archive).name}' did not extract to a valid backup directory "
            "— the archive may be corrupt or truncated. Nothing was restored."
        )
        return 1

    # Datastores whose archived data EXISTS but wasn't actually restored (its
    # container isn't running, or the restore itself failed) — surfaced loudly in
    # the final line so a partial restore can't read as a complete one (#282,
    # mirroring backup.py's own `skipped` list for the same "silent partial
    # success" failure mode, #177).
    skipped: list[str] = []

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
    # #288: `restore`'s own precondition is "services must be stopped", and
    # `stop` deliberately removes the app network — so without recreating it
    # here first (mirroring start.py), `compose up -d postgres` fails with
    # "network minder-network declared as external, but could not be found"
    # and every store below then reports "not running — restore skipped".
    if not docker.container_running("postgres"):
        infra.create_networks()
        docker.compose("up", "-d", "postgres")
        if not config.DRY_RUN:
            docker.wait_postgres_ready()

    # ── PostgreSQL ─────────────────────────────────────────────────────────
    if restore_dir and (restore_dir / "postgres.sql").is_file():
        log.spinner_start("Restoring PostgreSQL…")
        pgname = docker.container_name("postgres")
        if config.DRY_RUN:
            docker.run(
                "docker",
                "exec",
                "-i",
                pgname,
                "psql",
                "-U",
                "minder",
                "-d",
                "postgres",
                "-v",
                "ON_ERROR_STOP=1",
                "-f",
                "-",
            )
            ok = True
        else:
            ok = _restore_postgres(restore_dir / "postgres.sql")
        log.spinner_stop()
        if ok:
            log.success("PostgreSQL restored")
        else:
            log.warn("PostgreSQL restore had errors (partial restore possible)")
            skipped.append("PostgreSQL")

    # ── Neo4j (APOC cypher restore; #124 — restore was previously missing) ─
    # Load the exported cypher via cypher-shell -f. Password resolved inside the
    # container from its own $NEO4J_AUTH (never on the host cmdline). Assumes a
    # fresh/empty graph (the export uses CREATE, not MERGE) — matches the
    # "OVERWRITE current data" contract above.
    if (
        restore_dir
        and (restore_dir / "neo4j.cypher").is_file()
        and docker.container_running("neo4j")
    ):
        log.spinner_start("Restoring Neo4j…")
        nname = docker.container_name("neo4j")
        docker.run(
            "docker",
            "cp",
            str(restore_dir / "neo4j.cypher"),
            f"{nname}:/var/lib/neo4j/import/neo4j-restore.cypher",
        )
        restore_cmd = [
            "docker",
            "exec",
            nname,
            "bash",
            "-c",
            'cypher-shell -u neo4j -p "${NEO4J_AUTH#*/}" '
            "-f /var/lib/neo4j/import/neo4j-restore.cypher",
        ]
        if config.DRY_RUN:
            docker.run(*restore_cmd)
            ok = True
        else:
            ok = _run_bare(restore_cmd, stderr_null=True) == 0
        log.spinner_stop()
        if ok:
            log.success("Neo4j restored")
        else:
            log.warn("Neo4j restore had errors")
            skipped.append("Neo4j")
    elif restore_dir and (restore_dir / "neo4j.cypher").is_file():
        log.warn("Neo4j not running — restore skipped")
        skipped.append("Neo4j")

    # ── InfluxDB (raw data-dir snapshot restore; #177) ────────────────────
    # Symmetric to the backup snapshot: copy the tar in and extract to / so
    # /var/lib/influxdb3 is repopulated. Restart influxdb afterwards (the start
    # step the final message points to) so it re-opens the restored data dir.
    if (
        restore_dir
        and (restore_dir / "influxdb.tar.gz").is_file()
        and docker.container_running("influxdb")
    ):
        log.spinner_start("Restoring InfluxDB…")
        iname = docker.container_name("influxdb")
        ok = (
            docker.run(
                "docker",
                "cp",
                str(restore_dir / "influxdb.tar.gz"),
                f"{iname}:/tmp/influxdb.tar.gz",
            )
            == 0
            and docker.run(
                "docker",
                "exec",
                iname,
                "tar",
                "xzf",
                "/tmp/influxdb.tar.gz",
                "-C",
                "/",
            )
            == 0
        )
        log.spinner_stop()
        if ok:
            log.success("InfluxDB restored")
        else:
            log.warn("InfluxDB restore had errors")
            skipped.append("InfluxDB")
    elif restore_dir and (restore_dir / "influxdb.tar.gz").is_file():
        log.warn("InfluxDB not running — restore skipped")
        skipped.append("InfluxDB")

    # ── Qdrant (#56: copy in AND extract the same /tmp/qdrant.tar.gz) ──────
    if (
        restore_dir
        and (restore_dir / "qdrant.tar.gz").is_file()
        and docker.container_running("qdrant")
    ):
        log.spinner_start("Restoring Qdrant…")
        qname = docker.container_name("qdrant")
        ok = (
            docker.run(
                "docker",
                "cp",
                str(restore_dir / "qdrant.tar.gz"),
                f"{qname}:/tmp/qdrant.tar.gz",
            )
            == 0
            and docker.run(
                "docker", "exec", qname, "tar", "xzf", "/tmp/qdrant.tar.gz", "-C", "/"
            )
            == 0
        )
        log.spinner_stop()
        if ok:
            log.success("Qdrant restored")
        else:
            log.warn("Qdrant restore had errors")
            skipped.append("Qdrant")
    elif restore_dir and (restore_dir / "qdrant.tar.gz").is_file():
        log.warn("Qdrant not running — restore skipped")
        skipped.append("Qdrant")

    # ── RabbitMQ definitions ──────────────────────────────────────────────
    if (
        restore_dir
        and (restore_dir / "rabbitmq-definitions.json").is_file()
        and docker.container_running("rabbitmq")
    ):
        log.spinner_start("Restoring RabbitMQ definitions…")
        rname = docker.container_name("rabbitmq")
        docker.run(
            "docker",
            "cp",
            str(restore_dir / "rabbitmq-definitions.json"),
            f"{rname}:/tmp/rabbitmq-defs.json",
        )
        if config.DRY_RUN:
            docker.run(
                "docker",
                "exec",
                rname,
                "rabbitmqctl",
                "import_definitions",
                "/tmp/rabbitmq-defs.json",
            )
            ok = True
        else:
            ok = (
                _run_bare(
                    [
                        "docker",
                        "exec",
                        rname,
                        "rabbitmqctl",
                        "import_definitions",
                        "/tmp/rabbitmq-defs.json",
                    ],
                    stderr_null=True,
                )
                == 0
            )
        log.spinner_stop()
        if ok:
            log.success("RabbitMQ definitions restored")
        else:
            log.warn("RabbitMQ definitions restore had errors")
            skipped.append("RabbitMQ")
    elif restore_dir and (restore_dir / "rabbitmq-definitions.json").is_file():
        log.warn("RabbitMQ not running — restore skipped")
        skipped.append("RabbitMQ")

    shutil.rmtree(tmp_dir, ignore_errors=True)
    if skipped:
        log.warn(
            f"Restore complete — NOT restored: {', '.join(skipped)}. "
            f"Restart services: ./{config.SCRIPT_NAME} start"
        )
    else:
        log.success(
            f"Restore complete — restart services: ./{config.SCRIPT_NAME} start"
        )
    return 0
