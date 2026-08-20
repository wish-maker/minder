""".env helpers — ported from scripts/lib/env.sh (#7, Stage 2).

`get()` (bash `_env_get`), `gen_secret`, `sync_compose_env`, `fill_env_secrets`,
`write_default_env`, and the `prepare_env` orchestration are all ported (consumed
by the native install/start verbs). fill_env_secrets carries the #57 guard:
it refuses to auto-(re)generate secrets while a provisioned stack is running
(that would desync live services), unless MINDER_ALLOW_SECRET_REGEN=1.
"""

import os
import re
import secrets
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import config, docker, filelock, log

ENV_FILE = config.ENV_FILE
ENV_EXAMPLE = config.ENV_EXAMPLE
COMPOSE_ENV_FILE = config.COMPOSE_ENV_FILE
# Public (not _ENV_LOCK) -- ollama.py/tts_stt.py also read-modify-write .env and
# need this exact same lock file to get real mutual exclusion with fill_env_secrets
# below and with each other (#374's whole point: two concurrent setup.sh
# invocations must not interleave writes to the same file).
ENV_LOCK = ENV_FILE.parent / ".env.lock"

# Authoritative secret-key set → "length[:format]" (env.sh SECRET_SPEC). Smart-fill
# touches ONLY these keys; every other .env line is left exactly as written.
SECRET_SPEC = {
    "POSTGRES_PASSWORD": "32",
    "REDIS_PASSWORD": "32",
    "RABBITMQ_PASSWORD": "32",
    "MINIO_ROOT_PASSWORD": "32",
    "JWT_SECRET": "64",
    "NEO4J_AUTH": "16:neo4j/",
    "INFLUXDB_TOKEN": "40",
    "AUTHELIA_STORAGE_ENCRYPTION_KEY": "32",
    "AUTHELIA_SESSION_SECRET": "32",
    "AUTHELIA_IDENTITY_VALIDATION_RESET_PASSWORD_JWT_SECRET": "32",
    "GRAFANA_PASSWORD": "32",
    "WEBUI_SECRET_KEY": "32",
    # Inter-service auth for registry→marketplace AI-tool catalog sync (X-Service-Token).
    # One .env value passed to both containers, so a generated value matches on both
    # sides. Was skipped here → stayed empty → sync silently 401'd (#227).
    "SERVICE_SYNC_TOKEN": "32",
    # Authelia OIDC provider (#<issue>) -- hmac_secret signs Authelia's own
    # internal OIDC session/consent tokens. MINDER_OIDC_CLIENT_SECRET is the
    # plaintext confidential-client secret api-gateway sends on every token
    # exchange; render_authelia_config() separately argon2id-hashes this
    # same value for Authelia's own client_secret config, so both sides stay
    # in sync from one generated value without either side storing the
    # other's exact representation.
    "AUTHELIA_IDENTITY_PROVIDERS_OIDC_HMAC_SECRET": "32",
    "MINDER_OIDC_CLIENT_SECRET": "32",
    # Authelia `admin` account password, plaintext (#473) -- every clone of this
    # repo used to ship the exact same hardcoded users_database.yml hash.
    # render_users_database() argon2id-hashes this value into
    # users_database.rendered.yml; fill_env_secrets() below prints the
    # plaintext once, the moment it's freshly generated.
    "MINDER_AUTHELIA_ADMIN_PASSWORD": "32",
}

# Values matching this (case-sensitive substring) are treated as unset placeholders.
_PLACEHOLDER_RE = re.compile(r"CHANGEME|REPLACE_ME|change-this-to|my-super-secret")

# gen_secret() only ever emits lowercase hex.
_HEX_RE = re.compile(r"^[0-9a-f]+$")


def _looks_like_a_real_secret(value: str, spec: str) -> bool:
    """True if `value` plausibly came from gen_secret() per `spec` ("length[:format]"),
    rather than being a placeholder that slipped past _PLACEHOLDER_RE's literal-string
    check (#916: an all-zeros 68-char JWT_SECRET and a 60-char human-readable
    placeholder string -- neither containing any of _PLACEHOLDER_RE's substrings,
    and NEITHER the correct length for gen_secret(64)'s 128-char output -- both
    stayed live and unrotated on two real dev hosts).

    Three independent red flags, checked on the hex portion only (the `fmt` prefix
    for a prefixed spec like NEO4J_AUTH's "neo4j/" is a fixed literal, not part of
    the randomness, so it's stripped before any check runs):

    - wrong length for `spec` -- gen_secret(N) always emits exactly 2*N hex chars;
      both real placeholders above were also the wrong length, so this alone
      would have caught them.
    - not actually hex (gen_secret() output is always [0-9a-f]) -- catches a
      human-readable placeholder like "minder_jwt_secret_key_2026_..." outright
      even in the (unobserved so far) case where one happens to be the right length.
    - too few distinct hex digits for its length to plausibly be
      secrets.token_hex() output -- catches a degenerate low-entropy value like
      64 zero characters, which passes the pure-hex check on its own.

    This is intentionally stricter than the old bare-placeholder-substring check:
    an arbitrary hand-typed value that happens to be non-hex-shaped is no longer
    treated as "the user's real custom secret, leave it alone" -- it's now
    indistinguishable from a placeholder that just doesn't happen to contain
    "CHANGEME". fill_env_secrets()'s own #57 live-stack guard is the actual
    safety net against clobbering something in place on a running deployment;
    this function only decides whether a value NEEDS regenerating, not whether
    it's currently SAFE to.
    """
    length_str, _, fmt = spec.partition(":")
    length = int(length_str)
    hex_part = value[len(fmt) :] if fmt and value.startswith(fmt) else value
    if len(hex_part) != 2 * length:
        return False
    if not _HEX_RE.match(hex_part):
        return False
    # secrets.token_hex(N) for any real N used in SECRET_SPEC (>=8) draws from all
    # 16 hex digits essentially uniformly; requiring at least half of them present
    # catches a degenerate repeated/low-diversity value without false-flagging a
    # short-but-genuinely-random secret.
    if len(set(hex_part)) < min(8, len(hex_part) // 2):
        return False
    return True


# _sync_compose_env's DO-NOT-EDIT banner (config.sh printf block): "# " + 76 '='.
_COMPOSE_ENV_BANNER = (
    "# " + "=" * 76,
    "# DO NOT EDIT — generated by setup.sh from the root .env (single source of truth).",
    "# Edit ./.env and re-run setup.sh (start/restart) to regenerate this file.",
    "# " + "=" * 76,
)


def get(key: str) -> str:
    """Mirror env.sh _env_get: `grep -E "^KEY=" .env | cut -d= -f2-` — the value
    after the FIRST '='; "" when the key is absent or .env is unreadable. Multiple
    matching lines yield their values joined by newlines, exactly like the pipe.
    (Keys are fixed identifiers with no regex metachars, so a prefix match is
    equivalent to bash's `^KEY=` anchor.)
    """
    try:
        text = ENV_FILE.read_text(encoding="utf-8")
    except OSError:
        return ""
    out = [
        line.split("=", 1)[1]
        for line in text.splitlines()
        if line.startswith(f"{key}=")
    ]
    return "\n".join(out)


def gen_secret(nbytes: int = 32) -> str:
    """bash gen_secret: 2*nbytes hex chars. bash uses `openssl rand -hex` with a
    /dev/urandom fallback; secrets.token_hex is cross-platform, cryptographically
    secure, and needs neither — the observable contract (length + [0-9a-f]) holds."""
    return secrets.token_hex(nbytes)


def sync_compose_env() -> None:
    """bash _sync_compose_env: mirror the root .env to COMPOSE_ENV_FILE (the path
    docker compose reads) with a DO-NOT-EDIT banner. A COPY, not a symlink, for
    Windows + Pi. Silent. The .env body is passed through as raw bytes (like
    `cat`) so no line-ending translation can diverge from bash."""
    COMPOSE_ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        body = ENV_FILE.read_bytes()
    except OSError:
        body = b""
    banner = ("\n".join(_COMPOSE_ENV_BANNER) + "\n").encode("utf-8")
    with COMPOSE_ENV_FILE.open("wb") as fh:
        fh.write(banner + body)
    try:  # chmod 600 best-effort — no-op on Windows, mirrors bash's `|| true`
        COMPOSE_ENV_FILE.chmod(0o600)
    except OSError:
        pass


def sync_telegraf_config() -> None:
    """Seed the gitignored runtime telegraf.conf from the tracked template when it
    is absent, so the telegraf plugin writes its managed region to the RUNTIME copy
    and never dirties the tracked template. Mirrors sync_compose_env: silent and
    idempotent, and it MUST run before `compose up` — a missing bind-mount source
    is otherwise created by docker as an empty directory (the bind-mount footgun).

    Seed-if-absent preserves the plugin's managed region across restarts; only a
    fresh runtime file re-copies the template's static config. (A stale static
    section after a template bump is the known trade-off of not re-parsing the
    markers here — the plugin owns the region once seeded.)"""
    runtime = config.TELEGRAF_RUNTIME
    if runtime.exists():
        return
    try:
        body = config.TELEGRAF_TEMPLATE.read_bytes()
    except OSError:
        return  # no template (unexpected) — leave it to compose/plugin to surface
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_bytes(body)


def ensure_bundles_state_file() -> None:
    """Seed an empty ``bundles.state.json`` (``{}`` → everything enabled, the default)
    when it is absent, so it can be bind-mounted RW into the registry for the mutating
    bundle endpoints (#65 item-2). Like sync_telegraf_config it MUST run before
    ``compose up`` — a missing bind-mount source becomes a docker-created empty
    DIRECTORY (the bind-mount footgun). Mode 0666 because the registry runs as a
    non-root appuser and must be able to write it (secret-free by design — only bundle
    on/off flags). Seed-if-absent: never clobbers host- or API-written enable-state,
    and ``{}`` is behaviour-identical to an absent file so it stays gate-neutral."""
    state = config.BUNDLES_STATE
    try:
        if not state.exists():
            state.parent.mkdir(parents=True, exist_ok=True)
            state.write_text("{}\n", encoding="utf-8")
        # Ensure 0666 whether we just created it OR it already exists (the host CLI
        # writes it 0644, and the file is bind-mounted into the non-root registry
        # which must write it back). write_text truncates in place → the mode sticks.
        # Runs before every `up`, so it self-heals after a CLI write. Secret-free.
        state.chmod(0o666)
    except OSError:
        pass


def ensure_backup_jobs_dir() -> None:
    """Seed ``backup-jobs/`` (#870) when absent, so it can be bind-mounted RW into
    the registry for the backup/restore job-queue endpoints. Like
    ensure_bundles_state_file, MUST run before ``compose up`` — a missing bind-mount
    source becomes a docker-created empty directory owned by whatever ran `up`
    (usually root), which the non-root registry appuser then can't write into.
    Mode 0777 (not 0666 — this is a directory, needs the execute/traverse bit too)
    because job files are secret-free JSON metadata (id/action/archive name/status
    timestamps), never credentials. Idempotent: chmod runs every time so a stale
    mode self-heals on the next `up`, same as the bundles-state file."""
    jobs_dir = config.BACKUP_JOBS_DIR
    try:
        jobs_dir.mkdir(parents=True, exist_ok=True)
        jobs_dir.chmod(0o777)
    except OSError:
        pass


_OIDC_ISSUER_KEY = (
    config.REPO_ROOT
    / "docker"
    / "services"
    / "authelia"
    / "secrets"
    / "oidc_issuer.pem"
)


def ensure_oidc_issuer_key() -> None:
    """Generate Authelia's OIDC token-signing RSA key on first run (#<issue>).
    Authelia signs every OIDC ID/access token it issues with this key, so
    unlike the SECRET_SPEC values above it can't be a bare env-var token --
    Authelia's jwks.key config wants real PEM.

    Generated via a throwaway `docker run` (alpine + openssl) rather than a
    host-installed openssl binary: openssl is a required *nix prerequisite
    (preflight.py) but is NOT reliably on PATH on Windows hosts (hantal),
    where docker itself is guaranteed present since the whole platform runs
    through it. The key is captured straight off stdout as raw bytes (no
    volume mount, no host/container path translation to get wrong) and
    written with Python's own file I/O.

    Directly under docker/services/authelia/secrets/, matching the repo's
    existing bare `secrets/` .gitignore rule -- never committed, same as
    .env itself. Left alone on every subsequent run: regenerating it after
    Authelia has issued tokens against the old key would invalidate all of
    them, and unlike a password rotation there is no user-facing
    "re-enter credentials" story for that -- every active session breaks
    silently instead."""
    if _OIDC_ISSUER_KEY.exists():
        return
    _OIDC_ISSUER_KEY.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "alpine:3.20",
                "sh",
                "-c",
                "apk add --no-cache openssl >/dev/null 2>&1 && openssl genrsa 2048",
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        log.warn(f"Could not generate OIDC issuer key: {e}")
        return
    pem = result.stdout
    if not pem.strip().startswith(b"-----BEGIN"):
        log.warn("OIDC issuer key generation produced unexpected output")
        return
    _OIDC_ISSUER_KEY.write_bytes(pem)
    _chmod_600(_OIDC_ISSUER_KEY)
    log.success("Generated Authelia OIDC issuer key")


_AUTHELIA_CONFIG_SRC = _OIDC_ISSUER_KEY.parents[1] / "configuration.yml"
_AUTHELIA_CONFIG_RENDERED = _OIDC_ISSUER_KEY.parents[1] / "configuration.rendered.yml"
_OIDC_PLACEHOLDER = "__MINDER_OIDC_ISSUER_KEY_PEM__"
_OIDC_CLIENT_SECRET_PLACEHOLDER = "__MINDER_OIDC_CLIENT_SECRET_HASH__"
_AUTHELIA_IMAGE = "authelia/authelia:4.39.20"  # matches docker-compose.yml's pin


def _hash_oidc_client_secret() -> str:
    """Argon2id-hash MINDER_OIDC_CLIENT_SECRET via Authelia's own CLI in a
    throwaway container (the exact image already pinned in
    docker-compose.yml, so this never pulls anything the stack would not
    already need). A $plaintext$ secret was tried first: confirmed against
    a real Authelia instance to fail token exchange regardless of client
    auth method, even with byte-identical values on both sides -- a real
    hash is what actually works. Re-hashed fresh on every render (argon2's
    random salt makes each output different even for the same input) rather
    than cached, since the secret's plaintext value itself only changes via
    SECRET_SPEC's own regen guard, and hashing is cheap."""
    secret = get("MINDER_OIDC_CLIENT_SECRET")
    if not secret:
        return ""
    try:
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                _AUTHELIA_IMAGE,
                "authelia",
                "crypto",
                "hash",
                "generate",
                "argon2",
                "--password",
                secret,
                "--variant",
                "argon2id",
                "--memory",
                "32768",
                "--iterations",
                "3",
                "--parallelism",
                "2",
            ],
            check=True,
            capture_output=True,
            timeout=60,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        log.warn(f"Could not hash OIDC client secret: {e}")
        return ""
    # authelia's CLI prints "Digest: $argon2id$...\n" -- take the part after
    # the first ": ", stripped, whatever the exact prefix wording.
    line = result.stdout.strip()
    return line.split(": ", 1)[-1].strip() if ": " in line else line


def render_authelia_config() -> None:
    """Substitute the real OIDC issuer key + client secret hash into
    Authelia's config.

    configuration.yml (git-tracked) holds stable placeholders instead of key
    material; this writes configuration.rendered.yml (gitignored) with them
    replaced by the actual PEM (reindented as a YAML literal block scalar at
    the key's nesting depth -- 8 spaces + 2, matching that line's own
    indentation in the source) and the client secret's argon2id hash.

    Plain Python string substitution, deliberately NOT Authelia's own
    Go-template config-file filter: that route was tried first and abandoned
    after proving too fragile to debug reliably (raw double-curly-brace
    regions get parsed everywhere in the file, including inside YAML
    comments, and the engine's own error line numbers didn't correspond to
    anything inspectable). Runs on every prepare_env() call, unlike the
    key-generation above -- cheap, and needs to stay in sync if the source
    template changes, whereas the key itself must NOT be regenerated once
    issued."""
    try:
        template = _AUTHELIA_CONFIG_SRC.read_text(encoding="utf-8")
        pem = _OIDC_ISSUER_KEY.read_text(encoding="utf-8")
    except OSError as e:
        log.warn(f"Could not render Authelia config: {e}")
        return
    indented = "\n".join(f"          {line}" for line in pem.strip().splitlines())
    rendered = template.replace(_OIDC_PLACEHOLDER, f"|\n{indented}")
    secret_hash = _hash_oidc_client_secret()
    if secret_hash:
        rendered = rendered.replace(_OIDC_CLIENT_SECRET_PLACEHOLDER, f'"{secret_hash}"')
    try:
        if _AUTHELIA_CONFIG_RENDERED.is_dir():
            # Found live (Pi): Docker auto-creates a missing bind-mount SOURCE
            # path as a directory the first time a container using it is
            # created. If this ever races ahead of the first successful
            # render (or a prior render crashed before writing), every later
            # authelia recreate then fails ("not a directory") against this
            # stray directory forever -- self-heal instead of leaving that to
            # a manual `docker start` failure investigation.
            shutil.rmtree(_AUTHELIA_CONFIG_RENDERED)
        _AUTHELIA_CONFIG_RENDERED.write_text(rendered, encoding="utf-8")
    except OSError as e:
        log.warn(f"Could not write rendered Authelia config: {e}")


_USERS_DB_SRC = _OIDC_ISSUER_KEY.parents[1] / "users_database.yml"
_USERS_DB_RENDERED = _OIDC_ISSUER_KEY.parents[1] / "users_database.rendered.yml"
_ADMIN_PASSWORD_PLACEHOLDER = "__MINDER_AUTHELIA_ADMIN_PASSWORD_HASH__"


def _hash_admin_password() -> str:
    """Argon2id-hash MINDER_AUTHELIA_ADMIN_PASSWORD via Authelia's own CLI --
    identical approach to _hash_oidc_client_secret() (#473), same throwaway
    container, same reasoning: re-hashed fresh on every render since argon2's
    random salt makes each output different anyway, and hashing is cheap."""
    secret = get("MINDER_AUTHELIA_ADMIN_PASSWORD")
    if not secret:
        return ""
    try:
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                _AUTHELIA_IMAGE,
                "authelia",
                "crypto",
                "hash",
                "generate",
                "argon2",
                "--password",
                secret,
                "--variant",
                "argon2id",
                "--memory",
                "32768",
                "--iterations",
                "3",
                "--parallelism",
                "2",
            ],
            check=True,
            capture_output=True,
            timeout=60,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        log.warn(f"Could not hash Authelia admin password: {e}")
        return ""
    line = result.stdout.strip()
    return line.split(": ", 1)[-1].strip() if ": " in line else line


def render_users_database() -> None:
    """Substitute the real admin password hash into Authelia's user database
    (#473). users_database.yml (git-tracked) holds a stable placeholder
    instead of a hash that's identical across every clone of this repo; this
    writes users_database.rendered.yml (gitignored) with the real
    per-deployment hash. Same self-heal-a-stray-directory handling as
    render_authelia_config() (Docker auto-creates a missing bind-mount SOURCE
    as a directory) and the same reasoning for running on every prepare_env()
    call rather than caching."""
    try:
        template = _USERS_DB_SRC.read_text(encoding="utf-8")
    except OSError as e:
        log.warn(f"Could not render Authelia users database: {e}")
        return
    # users_database.yml already wraps the placeholder in double quotes, so
    # (unlike render_authelia_config()'s secret-hash substitution) no
    # additional quoting is needed here. Written even when hashing fails
    # (rendered = template, placeholder untouched) -- MUST always write a
    # real file, never skip it: a missing rendered path here is exactly the
    # Docker auto-creates-a-missing-bind-mount-as-a-directory bug already
    # fixed for configuration.rendered.yml.
    password_hash = _hash_admin_password()
    rendered = template
    if password_hash:
        rendered = rendered.replace(_ADMIN_PASSWORD_PLACEHOLDER, password_hash)
    try:
        if _USERS_DB_RENDERED.is_dir():
            shutil.rmtree(_USERS_DB_RENDERED)
        _USERS_DB_RENDERED.write_text(rendered, encoding="utf-8")
    except OSError as e:
        log.warn(f"Could not write rendered Authelia users database: {e}")


def _chmod_600(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        pass


# #57: stateful cores whose credentials would desync if secrets are regenerated
# while they are running. redis/minio re-read their password on recreate; postgres/
# neo4j/rabbitmq keep the volume password (recreate ignores the env), so a client
# that gets the freshly-generated secret can no longer authenticate.
_STATEFUL_CORES = ("postgres", "redis", "neo4j", "rabbitmq", "minio")


def _regen_allowed() -> bool:
    """MINDER_ALLOW_SECRET_REGEN=1|true|yes → explicit opt-in to rotate secrets on a
    live stack (same truthy set as DRY_RUN)."""
    return config._truthy(os.environ.get("MINDER_ALLOW_SECRET_REGEN", ""))


def _live_core() -> "str | None":
    """First running stateful-core service (short name), or None — the signal that
    the stack is already provisioned and secret regeneration would desync it."""
    for svc in _STATEFUL_CORES:
        if docker.container_running(svc):
            return svc
    return None


def _first_env_value(raw: str, key: str) -> "str | None":
    """First `key=` line's value in raw .env text, or None if the key is absent
    (bash: grep ^key= | head -n1 | cut -d= -f2-, with a __MISSING__ sentinel)."""
    for line in raw.split("\n"):
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1]
    return None


def fill_env_secrets() -> None:
    """bash _fill_env_secrets: generate a secret for each SECRET_SPEC key whose
    value is MISSING/EMPTY/a placeholder/(for prefixed specs) the bare prefix.
    Real user values are left untouched. Backs up .env before rewriting. SILENT
    no-op when nothing needs filling — this is what keeps the gate's start/stop/
    restart traces unchanged, so it must stay silent.

    Holds an advisory lock (#374) for the whole read-modify-write so two concurrent
    setup.sh invocations can't interleave writes and corrupt .env."""
    with filelock.locked(ENV_LOCK):
        try:
            raw = ENV_FILE.read_text(encoding="utf-8")
        except OSError:
            raw = ""

        to_fill = []
        for key, spec in SECRET_SPEC.items():
            fmt = spec.split(":", 1)[1] if ":" in spec else ""
            value = _first_env_value(raw, key)
            if (
                value is None
                or value == ""
                or _PLACEHOLDER_RE.search(value)
                or (fmt and value == fmt)
                or not _looks_like_a_real_secret(value, spec)
            ):
                to_fill.append(key)

        if not to_fill:
            return  # fully populated → silent no-op (gate-critical)

        to_fill.sort()  # deterministic log/apply order (spec iteration order is arbitrary)

        # #57: refuse to auto-(re)generate secrets while a provisioned stack is running —
        # doing so would mirror new secrets into docker/.env and let start_services
        # recreate the stateful cores, desyncing live services (redis/minio re-read their
        # password on recreate). Only reached when secrets ACTUALLY need filling; the
        # normal full-.env path returned above untouched, so healthy start/restart is
        # unaffected. Override with MINDER_ALLOW_SECRET_REGEN=1 to rotate intentionally.
        live = None if _regen_allowed() else _live_core()
        if live:
            joined = ", ".join(to_fill)
            log.error(
                f"Refusing to regenerate .env secrets — a provisioned stack is already running ({live})"
            )
            log.detail(f"Missing/placeholder secrets: {joined}")
            log.detail(
                "Regenerating would desync live services (redis/minio re-read their password on recreate)."
            )
            log.detail(
                "Fix: restore the real secrets into .env, or set MINDER_ALLOW_SECRET_REGEN=1 to rotate intentionally."
            )
            raise SystemExit(1)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup = ENV_FILE.parent / f".env.backup-{ts}"
        backup.write_bytes(ENV_FILE.read_bytes())
        # A full plaintext copy of every platform secret -- left at the OS
        # default umask (commonly world-readable) otherwise, unlike ENV_FILE
        # itself which _chmod_600's below. Nothing else ever secures or
        # cleans up old .env.backup-* files (confirmed via repo-wide grep).
        _chmod_600(backup)
        log.detail(f"Backed up .env → {backup.name}")

        for key in to_fill:
            spec = SECRET_SPEC[key]
            length = int(spec.split(":", 1)[0])
            fmt = spec.split(":", 1)[1] if ":" in spec else ""
            new_secret = f"{fmt}{gen_secret(length)}"
            if re.search(rf"(?m)^{re.escape(key)}=", raw):
                # sed "s|^key=.*|key=new|" — replace every matching line (function
                # replacement so hex/prefix is never treated as a backreference).
                raw = re.sub(
                    rf"(?m)^{re.escape(key)}=.*", lambda _m: f"{key}={new_secret}", raw
                )
            else:
                raw += f"{key}={new_secret}\n"  # bash printf … >> .env (no separator)
            log.detail(f"✓ Generated secret for {key}")
            if key == "MINDER_AUTHELIA_ADMIN_PASSWORD":
                # The one secret a human actually has to type back in (every
                # other SECRET_SPEC value is only ever read programmatically
                # by a service) -- print it once, now, since it's never shown
                # again. log.detail() (unlike warn/success/error) never
                # appends to the on-disk log file, so the plaintext itself
                # never gets persisted anywhere but .env (#473).
                log.section("🔑 Authelia Admin Password (generated)")
                log.warn("Record this now -- it will not be shown again.")
                log.detail("Username: admin")
                log.detail(f"Password: {new_secret}")

        with ENV_FILE.open("w", encoding="utf-8", newline="") as fh:
            fh.write(raw)
        log.success(f"{len(to_fill)} secret(s) generated/healed in .env")


# _write_default_env's heredoc body — extracted verbatim from env.sh (unquoted
# heredoc). {date} ← UTC now; <GEN:N> ← an INDEPENDENT gen_secret(N) each.
_DEFAULT_ENV_TEMPLATE = """\
# Minder Platform — Environment Configuration (LEGACY FALLBACK)
# Generated: {date}
# ⚠️  This is an INCOMPLETE fallback configuration!
#     Please restore .env.example from version control

# ── Core ────────────────────────────────────────────────────
ENVIRONMENT=development
LOG_LEVEL=INFO

# ── PostgreSQL ───────────────────────────────────────────────
POSTGRES_USER=minder
POSTGRES_PASSWORD=<GEN:32>
POSTGRES_DB=minder

# ── Redis ────────────────────────────────────────────────────
REDIS_PASSWORD=<GEN:32>

# ── RabbitMQ ─────────────────────────────────────────────────
RABBITMQ_PASSWORD=<GEN:32>

# ── MinIO ─────────────────────────────────────────────────────
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=<GEN:32>

# ── Auth & Security ──────────────────────────────────────────
JWT_SECRET=<GEN:64>
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=60

# ── Neo4j ────────────────────────────────────────────────────
NEO4J_AUTH=neo4j/<GEN:16>

# ── InfluxDB ─────────────────────────────────────────────────
INFLUXDB_TOKEN=<GEN:40>
INFLUXDB_ORG=minder
INFLUXDB_BUCKET=metrics

# ── Authelia ─────────────────────────────────────────────────
AUTHELIA_STORAGE_ENCRYPTION_KEY=<GEN:32>
AUTHELIA_SESSION_SECRET=<GEN:32>
AUTHELIA_IDENTITY_VALIDATION_RESET_PASSWORD_JWT_SECRET=<GEN:32>
AUTHELIA_IDENTITY_PROVIDERS_OIDC_HMAC_SECRET=<GEN:32>
MINDER_OIDC_CLIENT_SECRET=<GEN:32>
MINDER_AUTHELIA_ADMIN_PASSWORD=<GEN:32>

# ── Grafana ──────────────────────────────────────────────────
GRAFANA_ADMIN_USER=admin
GRAFANA_PASSWORD=<GEN:32>

# ── OpenWebUI ────────────────────────────────────────────────
WEBUI_SECRET_KEY=<GEN:32>
WEBUI_AUTH=true

# ── Traefik ───────────────────────────────────────────────────
ACME_EMAIL=admin@minder.local
TRAEFIK_TRUSTED_IPS=192.168.0.0/16,10.0.0.0/8,172.16.0.0/12,127.0.0.1/32

# ── Ollama ───────────────────────────────────────────────────
OLLAMA_AUTOMATIC_PULL=true
OLLAMA_MODELS=llama3.2,nomic-embed-text
OLLAMA_LLM_MODEL=llama3.2
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
# Set by 'ollama-mode failover <url>' (host:port of the external primary). Non-empty
# means failover mode: the ollama-router prefers this primary and falls back to the
# internal container. Empty means internal/external mode (see OLLAMA_BASE_URL).
OLLAMA_FAILOVER_PRIMARY=

# ── Models ─────────────────────────────────────────────────────
DEFAULT_BASE_MODEL=llama3.2

"""


def write_default_env() -> None:
    """bash _write_default_env: the incomplete fallback .env, used only when
    .env.example is missing. Random per-key secrets + a UTC generation date."""
    log.warn("No .env.example found — using legacy fallback (incomplete)")
    log.detail("Consider re-cloning repository or restoring .env.example")

    date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    content = _DEFAULT_ENV_TEMPLATE.replace("{date}", date)
    content = re.sub(r"<GEN:(\d+)>", lambda m: gen_secret(int(m.group(1))), content)
    with ENV_FILE.open("w", encoding="utf-8", newline="") as fh:
        fh.write(content)
    log.success("Generated .env with secure random secrets (fallback mode)")


def _upsert_env_key(key: str, value: str) -> None:
    """Set KEY=value in .env — replace the line if present, else append. Silent.

    Locked (#374) -- this is a read-modify-write of the same .env fill_env_secrets
    above writes; without the lock, a concurrent setup.sh invocation's write here
    could interleave with (and silently discard half of) that one."""
    with filelock.locked(ENV_LOCK):
        try:
            lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        out, found = [], False
        for ln in lines:
            if ln.split("=", 1)[0] == key:
                out.append(f"{key}={value}")
                found = True
            else:
                out.append(ln)
        if not found:
            out.append(f"{key}={value}")
        ENV_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")


def ensure_docker_gid() -> None:
    """Record the host 'docker' group's gid in .env as DOCKER_GID (#11) so compose's
    `group_add: ${DOCKER_GID:-0}` actually grants telegraf/plugin-registry read
    access to a root:docker docker.sock when they run non-root. Silent; a no-op off
    POSIX / when there's no docker group / when already correct — the `:-0` fallback
    covers those (dev hosts where docker.sock isn't group-gated the same way)."""
    try:
        import grp  # POSIX-only; ImportError on Windows

        gid = str(grp.getgrnam("docker").gr_gid)  # type: ignore[attr-defined]
    except (ImportError, KeyError, OSError):
        return
    if get("DOCKER_GID") != gid:
        _upsert_env_key("DOCKER_GID", gid)


def prepare_env() -> None:
    """bash prepare_env: self-healing provisioning (install/start/restart). Create
    .env from .env.example (or the fallback), heal missing secrets, chmod 600,
    mirror to the compose .env. Idempotent + silent when .env is already full."""
    if not ENV_FILE.exists():
        ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
        if ENV_EXAMPLE.is_file():
            ENV_FILE.write_bytes(ENV_EXAMPLE.read_bytes())
            log.success("Created .env from .env.example")
        else:
            log.info("No .env.example found — generating configuration")
            write_default_env()

    fill_env_secrets()
    ensure_docker_gid()
    _chmod_600(ENV_FILE)
    sync_compose_env()
    sync_telegraf_config()
    ensure_bundles_state_file()
    ensure_backup_jobs_dir()
    ensure_oidc_issuer_key()
    render_authelia_config()
    render_users_database()
