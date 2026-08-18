"""Unit tests for `doctor.run()`'s diagnostic sections (scripts/setup/doctor.py).

test_setup_doctor.py already covers `_WEAK_RE` directly -- `run()` itself (the
RAM/disk/.env/port/health/volume/version-drift checks that make up ~90% of this
module) had zero direct coverage. docker.capture/tcp_open, log, config, and
versions.version_drift_report are all monkeypatched -- no real Docker/network.

capfd (not capsys) because log._emit writes to sys.stdout.buffer, matching the
established convention in test_setup_health.py.
"""

import pytest

from scripts.setup import doctor

# The five docker.capture() call sites, keyed by a distinguishing token so a
# routing fake can tell them apart without depending on exact argv order.
_DEFAULT_CAPTURES = {
    ("docker", "--version"): "Docker version 24.0.0",
    ("docker", "compose", "version", "--short"): "2.20.0",
    ("docker", "info", "--format", "{{.MemTotal}}"): str(8 * 1024**3),  # 8GB
    ("docker", "ps", "--format", "{{.Ports}}"): "",
    (
        "docker",
        "ps",
        "--filter",
        "health=unhealthy",
        "--format",
        "{{.Names}}",
    ): "",
    ("docker", "ps", "--format", "{{.Names}}"): "minder-api-gateway",
    ("docker", "volume", "ls", "-q", "--filter", "dangling=true"): "",
}


def _routed_capture(overrides=None):
    captures = dict(_DEFAULT_CAPTURES)
    captures.update(overrides or {})

    def _capture(argv):
        return captures.get(tuple(argv), "")

    return _capture


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """A fully healthy baseline: enough RAM/disk, a correctly-permissioned .env
    with no weak secrets, every port free, no unhealthy containers, no dangling
    volumes, version check skipped. Individual tests override one seam at a
    time to exercise that section's warning branch."""
    monkeypatch.setattr(doctor.docker, "capture", _routed_capture())
    monkeypatch.setattr(doctor.docker, "tcp_open", lambda host, port, timeout=1: False)
    monkeypatch.setattr(
        doctor.shutil,
        "disk_usage",
        lambda path: type("U", (), {"free": 50 * 1024**3})(),
    )
    env_file = tmp_path / ".env"
    env_file.write_text("DB_PASSWORD=a-genuinely-random-secret\n# comment\nEMPTY=\n")
    env_file.chmod(0o600)
    monkeypatch.setattr(doctor.config, "ENV_FILE", env_file)
    monkeypatch.setattr(doctor.config, "SKIP_VERSION_CHECK", True)
    return env_file


def test_all_clean_reports_no_issues(clean_env, capfd):
    rc = doctor.run()
    out = capfd.readouterr().out
    assert rc == 0
    assert "No issues found" in out


# ── Docker RAM ────────────────────────────────────────────────────────────────


def test_low_ram_warns_and_counts_issue(clean_env, monkeypatch, capfd):
    monkeypatch.setattr(
        doctor.docker,
        "capture",
        _routed_capture(
            {("docker", "info", "--format", "{{.MemTotal}}"): str(2 * 1024**3)}
        ),
    )
    doctor.run()
    out = capfd.readouterr().out
    assert "only 2GB RAM" in out
    assert "1 issue(s) found" in out


def test_unparseable_ram_defaults_to_zero_and_warns(clean_env, monkeypatch, capfd):
    monkeypatch.setattr(
        doctor.docker,
        "capture",
        _routed_capture({("docker", "info", "--format", "{{.MemTotal}}"): "garbage"}),
    )
    doctor.run()
    out = capfd.readouterr().out
    assert "only 0GB RAM" in out


# ── Disk ───────────────────────────────────────────────────────────────────────


def test_low_disk_warns_and_counts_issue(clean_env, monkeypatch, capfd):
    monkeypatch.setattr(
        doctor.shutil,
        "disk_usage",
        lambda path: type("U", (), {"free": 5 * 1024**3})(),
    )
    doctor.run()
    out = capfd.readouterr().out
    assert "Low disk space" in out
    assert "1 issue(s) found" in out


def test_disk_check_oserror_is_tolerated(clean_env, monkeypatch, capfd):
    def _boom(path):
        raise OSError("no such device")

    monkeypatch.setattr(doctor.shutil, "disk_usage", _boom)
    doctor.run()
    out = capfd.readouterr().out
    assert "No issues found" in out  # falls back to free_gb=999, never warns


# ── Environment (.env) ─────────────────────────────────────────────────────────


def test_missing_env_file_warns_and_counts_issue(
    clean_env, monkeypatch, capfd, tmp_path
):
    monkeypatch.setattr(doctor.config, "ENV_FILE", tmp_path / "does-not-exist.env")
    doctor.run()
    out = capfd.readouterr().out
    assert ".env not found" in out
    assert "1 issue(s) found" in out


def test_wrong_permissions_warns_and_counts_issue(clean_env, capfd):
    clean_env.chmod(0o644)
    doctor.run()
    out = capfd.readouterr().out
    assert "permissions are" in out
    assert "1 issue(s) found" in out


class _FakeOSName:
    """Shadows doctor's OWN `os` name binding with name='nt', delegating
    everything else to the real module -- avoids mutating the process-global
    os.name, which unrelated code (including pathlib's own Path dispatch for
    any Path constructed while it's patched) could observe."""

    def __init__(self, real_os, name):
        self._real = real_os
        self.name = name

    def __getattr__(self, attr):
        return getattr(self._real, attr)


def test_windows_skips_permission_enforcement_without_flagging_an_issue(
    clean_env, monkeypatch, capfd
):
    # real chmod(0o600) is a documented no-op on Windows (env.py) -- st_mode
    # comes back ~0o666 regardless, so the permission check must be skipped
    # there rather than flagging a permanent false issue on every run.
    clean_env.chmod(0o644)
    monkeypatch.setattr(doctor, "os", _FakeOSName(doctor.os, "nt"))

    doctor.run()

    out = capfd.readouterr().out
    assert "not enforced on Windows" in out
    assert "permissions are" not in out
    assert "No issues found" in out


class _FakeOSStatFails:
    """Shadows doctor's OWN `os` name binding (doctor.os), not the real global
    `os` module -- doctor.py's only os.* use is `os.stat(config.ENV_FILE)`, but
    pathlib's OWN internals (config.ENV_FILE.is_file(), called earlier in the
    same run()) also route through the real os.stat, so patching that globally
    would break the is_file() check too."""

    def __init__(self, real_os, stat_error):
        self._real = real_os
        self._stat_error = stat_error

    def stat(self, path):
        raise self._stat_error

    def __getattr__(self, name):
        return getattr(self._real, name)


def test_stat_oserror_reports_unknown_permissions(clean_env, monkeypatch, capfd):
    monkeypatch.setattr(
        doctor, "os", _FakeOSStatFails(doctor.os, OSError("permission denied"))
    )
    doctor.run()
    out = capfd.readouterr().out
    assert "permissions are ??? " in out


def test_weak_secret_detected_warns_and_counts_issue(clean_env, capfd):
    clean_env.write_text("DB_PASSWORD=changeme\n")
    clean_env.chmod(0o600)
    doctor.run()
    out = capfd.readouterr().out
    assert "Weak value detected for DB_PASSWORD" in out
    assert "1 issue(s) found" in out


class _FakeEnvPath:
    """Delegates to a real Path for every operation doctor.py needs
    (is_file/os.stat via __fspath__) except read_text, which raises --
    avoids monkeypatching pathlib.Path.read_text globally (it's the real
    class, shared with pytest's own internals)."""

    def __init__(self, real_path, read_text_error):
        self._real = real_path
        self._read_text_error = read_text_error

    def is_file(self):
        return self._real.is_file()

    def read_text(self, *args, **kwargs):
        raise self._read_text_error

    def __fspath__(self):
        return str(self._real)


def test_env_read_oserror_is_tolerated(clean_env, monkeypatch, capfd):
    monkeypatch.setattr(
        doctor.config, "ENV_FILE", _FakeEnvPath(clean_env, OSError("io error"))
    )
    doctor.run()  # must not raise
    out = capfd.readouterr().out
    assert "No obvious weak secrets" in out  # zero lines -> zero weak matches


# ── Port availability ─────────────────────────────────────────────────────────


def test_port_open_and_owned_by_minder_is_ok(clean_env, monkeypatch, capfd):
    monkeypatch.setattr(
        doctor.docker,
        "capture",
        _routed_capture(
            {("docker", "ps", "--format", "{{.Ports}}"): "0.0.0.0:5432->5432/tcp"}
        ),
    )
    monkeypatch.setattr(
        doctor.docker, "tcp_open", lambda host, port, timeout=1: port == 5432
    )
    doctor.run()
    out = capfd.readouterr().out
    assert ":5432 — in use by Minder" in out
    assert "No issues found" in out


def test_port_open_but_not_owned_by_minder_warns_and_counts_issue(
    clean_env, monkeypatch, capfd
):
    monkeypatch.setattr(
        doctor.docker, "tcp_open", lambda host, port, timeout=1: port == 5432
    )
    doctor.run()
    out = capfd.readouterr().out
    assert ":5432 — in use by another process" in out
    assert "1 issue(s) found" in out


# ── Container health ───────────────────────────────────────────────────────────


def test_unhealthy_containers_warns_counts_issue_and_lists_names(
    clean_env, monkeypatch, capfd
):
    monkeypatch.setattr(
        doctor.docker,
        "capture",
        _routed_capture(
            {
                (
                    "docker",
                    "ps",
                    "--filter",
                    "health=unhealthy",
                    "--format",
                    "{{.Names}}",
                ): "minder-rag-pipeline"
            }
        ),
    )
    doctor.run()
    out = capfd.readouterr().out
    assert "Unhealthy containers:" in out
    assert "minder-rag-pipeline" in out
    assert "1 issue(s) found" in out


def test_no_unhealthy_containers_reports_running_count(clean_env, monkeypatch, capfd):
    monkeypatch.setattr(
        doctor.docker,
        "capture",
        _routed_capture(
            {
                ("docker", "ps", "--format", "{{.Names}}"): (
                    "minder-api-gateway\nminder-rag-pipeline\nother-unrelated"
                )
            }
        ),
    )
    doctor.run()
    out = capfd.readouterr().out
    assert "2 containers running, none unhealthy" in out


# ── Docker volumes: dangling>5 warns but (matching the ported bash cmd_doctor,
# see scripts/lib/commands.sh, and doctor_verify.sh's structural parity check)
# does NOT increment the issue counter -- characterized here, not "fixed",
# since changing it would diverge from the bash implementation it's verified
# against. ──────────────────────────────────────────────────────────────────


def test_many_dangling_volumes_warns_without_counting_as_an_issue(
    clean_env, monkeypatch, capfd
):
    monkeypatch.setattr(
        doctor.docker,
        "capture",
        _routed_capture(
            {
                ("docker", "volume", "ls", "-q", "--filter", "dangling=true"): (
                    "\n".join(f"vol{i}" for i in range(6))
                )
            }
        ),
    )
    doctor.run()
    out = capfd.readouterr().out
    assert "6 dangling volumes" in out
    assert "No issues found" in out  # NOT counted, matching bash cmd_doctor


def test_few_dangling_volumes_is_ok(clean_env, monkeypatch, capfd):
    monkeypatch.setattr(
        doctor.docker,
        "capture",
        _routed_capture(
            {
                (
                    "docker",
                    "volume",
                    "ls",
                    "-q",
                    "--filter",
                    "dangling=true",
                ): "vol1\nvol2"
            }
        ),
    )
    doctor.run()
    out = capfd.readouterr().out
    assert "Dangling volumes: 2" in out


# ── Image version drift ────────────────────────────────────────────────────────


def test_version_check_skipped_message(clean_env, capfd):
    doctor.run()
    out = capfd.readouterr().out
    assert "Version check skipped" in out


def test_version_drift_found_counts_issue(clean_env, monkeypatch, capfd):
    monkeypatch.setattr(doctor.config, "SKIP_VERSION_CHECK", False)
    monkeypatch.setattr(doctor.versions, "version_drift_report", lambda verbose: 2)
    doctor.run()
    out = capfd.readouterr().out
    assert "1 issue(s) found" in out


def test_no_version_drift_no_issue(clean_env, monkeypatch, capfd):
    monkeypatch.setattr(doctor.config, "SKIP_VERSION_CHECK", False)
    monkeypatch.setattr(doctor.versions, "version_drift_report", lambda verbose: 0)
    doctor.run()
    out = capfd.readouterr().out
    assert "No issues found" in out


# ── Aggregate: multiple simultaneous issues sum correctly ─────────────────────


def test_multiple_issues_sum_in_the_final_count(clean_env, monkeypatch, capfd):
    monkeypatch.setattr(
        doctor.docker,
        "capture",
        _routed_capture(
            {
                ("docker", "info", "--format", "{{.MemTotal}}"): str(2 * 1024**3),
                (
                    "docker",
                    "ps",
                    "--filter",
                    "health=unhealthy",
                    "--format",
                    "{{.Names}}",
                ): "minder-rag-pipeline",
            }
        ),
    )
    clean_env.chmod(0o644)
    doctor.run()
    out = capfd.readouterr().out
    # low RAM + wrong perms + unhealthy container = 3
    assert "3 issue(s) found" in out
