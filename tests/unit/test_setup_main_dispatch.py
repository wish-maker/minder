"""Unit tests for scripts/setup/__main__.py's command dispatch -- _positional,
_command, main()'s per-verb argument parsing/routing, and _entry()'s cleanup
epilogue. test_setup_help_routing.py already covers the `--help`-anywhere
routing bug (#234 item 5); this file covers everything else. Every verb
module is monkeypatched to a recorder -- no real Docker/filesystem access.
"""

import pytest

from scripts.setup import __main__ as entry


@pytest.fixture(autouse=True)
def _restore_mutated_config(monkeypatch):
    # main() writes straight to config.DRY_RUN/VERBOSE/CLEAN_DANGLING.
    monkeypatch.setattr(entry.config, "DRY_RUN", False)
    monkeypatch.setattr(entry.config, "VERBOSE", False)
    monkeypatch.setattr(entry.config, "CLEAN_DANGLING", False)


def _spy(monkeypatch, module, name, retval=0):
    calls = []

    def _fake(*args, **kwargs):
        calls.append((args, kwargs))
        return retval

    monkeypatch.setattr(module, name, _fake)
    return calls


# ── _positional / _command ────────────────────────────────────────────────────


def test_positional_strips_global_flags():
    argv = ["--dry-run", "status", "--verbose", "--json"]
    assert entry._positional(argv) == ["status"]


def test_command_defaults_to_install_when_nothing_positional():
    assert entry._command(["--dry-run", "--verbose"]) == "install"


def test_command_returns_first_positional():
    assert entry._command(["restart", "redis"]) == "restart"


# ── global flags ───────────────────────────────────────────────────────────────


def test_dry_run_flag_sets_config(monkeypatch):
    _spy(monkeypatch, entry.start_module, "run")
    entry.main(["--dry-run", "start"])
    assert entry.config.DRY_RUN is True


def test_verbose_flag_sets_config(monkeypatch):
    _spy(monkeypatch, entry.start_module, "run")
    entry.main(["--verbose", "start"])
    assert entry.config.VERBOSE is True


# ── version ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("argv", [["version"], ["-V"], ["--version"], ["status", "-V"]])
def test_version_verbs_print_version_and_skip_dispatch(monkeypatch, argv):
    emitted = []
    monkeypatch.setattr(entry.log, "_emit", lambda msg: emitted.append(msg))
    status_calls = _spy(monkeypatch, entry.status_module, "run")

    rc = entry.main(argv)

    assert rc == 0
    assert any(entry.config.SCRIPT_VERSION in m for m in emitted)
    assert status_calls == []


# ── simple pass-through verbs ──────────────────────────────────────────────────


def test_ollama_mode_passes_mode_and_url(monkeypatch):
    calls = _spy(monkeypatch, entry.ollama_module, "run")
    entry.main(["ollama-mode", "external", "http://gpu:11434"])
    assert calls == [(("external", "http://gpu:11434"), {})]


def test_ollama_mode_defaults_when_no_args(monkeypatch):
    calls = _spy(monkeypatch, entry.ollama_module, "run")
    entry.main(["ollama-mode"])
    assert calls == [(("", ""), {})]


def test_tts_stt_mode_passes_mode_and_url(monkeypatch):
    calls = _spy(monkeypatch, entry.tts_stt_module, "run")
    entry.main(["tts-stt-mode", "internal"])
    assert calls == [(("internal", ""), {})]


def test_sync_postgres_password_dispatches(monkeypatch):
    calls = _spy(monkeypatch, entry.secrets_module, "sync_postgres_password")
    entry.main(["sync-postgres-password"])
    assert calls == [((), {})]


def test_migrate_defaults_to_head(monkeypatch):
    calls = _spy(monkeypatch, entry.migrate_module, "run")
    entry.main(["migrate"])
    assert calls == [(("head",), {})]


def test_migrate_passes_explicit_target(monkeypatch):
    calls = _spy(monkeypatch, entry.migrate_module, "run")
    entry.main(["migrate", "abc123"])
    assert calls == [(("abc123",), {})]


def test_logs_defaults_service_and_lines(monkeypatch):
    calls = _spy(monkeypatch, entry.logs_module, "run")
    entry.main(["logs"])
    assert calls == [(("", "100"), {})]


def test_logs_passes_explicit_service_and_lines(monkeypatch):
    calls = _spy(monkeypatch, entry.logs_module, "run")
    entry.main(["logs", "api-gateway", "250"])
    assert calls == [(("api-gateway", "250"), {})]


def test_shell_passes_service(monkeypatch):
    calls = _spy(monkeypatch, entry.shell_module, "run")
    entry.main(["shell", "postgres"])
    assert calls == [(("postgres",), {})]


def test_uninstall_passes_purge_arg(monkeypatch):
    calls = _spy(monkeypatch, entry.uninstall_module, "run")
    entry.main(["uninstall", "--purge"])
    assert calls == [(("--purge",), {})]


def test_uninstall_defaults_to_empty(monkeypatch):
    calls = _spy(monkeypatch, entry.uninstall_module, "run")
    entry.main(["uninstall"])
    assert calls == [(("",), {})]


def test_start_takes_no_args(monkeypatch):
    calls = _spy(monkeypatch, entry.start_module, "run")
    entry.main(["start"])
    assert calls == [((), {})]


def test_restart_passes_service(monkeypatch):
    calls = _spy(monkeypatch, entry.restart_module, "run")
    entry.main(["restart", "redis"])
    assert calls == [(("redis",), {})]


def test_restart_defaults_to_empty(monkeypatch):
    calls = _spy(monkeypatch, entry.restart_module, "run")
    entry.main(["restart"])
    assert calls == [(("",), {})]


def test_update_defaults_to_empty(monkeypatch):
    calls = _spy(monkeypatch, entry.update_module, "run")
    entry.main(["update"])
    assert calls == [(("",), {})]


def test_update_passes_check_flag(monkeypatch):
    calls = _spy(monkeypatch, entry.update_module, "run")
    entry.main(["update", "--check"])
    assert calls == [(("--check",), {})]


def test_backup_takes_no_args(monkeypatch):
    calls = _spy(monkeypatch, entry.backup_module, "run")
    entry.main(["backup"])
    assert calls == [((), {})]


def test_restore_passes_archive(monkeypatch):
    calls = _spy(monkeypatch, entry.restore_module, "run")
    entry.main(["restore", "/backups/x.tar.gz"])
    assert calls == [(("/backups/x.tar.gz",), {})]


def test_doctor_takes_no_args(monkeypatch):
    calls = _spy(monkeypatch, entry.doctor_module, "run")
    entry.main(["doctor"])
    assert calls == [((), {})]


# ── stop ────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("flag", ["--clean", "--clean-dangling"])
def test_stop_clean_flags_set_config(monkeypatch, flag):
    _spy(monkeypatch, entry.stop_module, "run")
    entry.main(["stop", flag])
    assert entry.config.CLEAN_DANGLING is True


def test_stop_without_clean_flag_leaves_config_false(monkeypatch):
    _spy(monkeypatch, entry.stop_module, "run")
    entry.main(["stop"])
    assert entry.config.CLEAN_DANGLING is False


# ── status flag parsing ───────────────────────────────────────────────────────


def test_status_defaults(monkeypatch):
    calls = _spy(monkeypatch, entry.status_module, "run")
    entry.main(["status"])
    assert calls == [
        (
            (),
            {
                "json_mode": False,
                "watch": 0,
                "report": False,
                "report_path": "",
                "fix": False,
            },
        )
    ]


def test_status_json_flag(monkeypatch):
    calls = _spy(monkeypatch, entry.status_module, "run")
    entry.main(["status", "--json"])
    assert calls[0][1]["json_mode"] is True


def test_status_watch_with_explicit_seconds(monkeypatch):
    calls = _spy(monkeypatch, entry.status_module, "run")
    entry.main(["status", "--watch", "15"])
    assert calls[0][1]["watch"] == 15


def test_status_watch_without_a_digit_defaults_to_30(monkeypatch):
    calls = _spy(monkeypatch, entry.status_module, "run")
    entry.main(["status", "--watch"])
    assert calls[0][1]["watch"] == 30


def test_status_watch_followed_by_non_digit_defaults_to_30(monkeypatch):
    calls = _spy(monkeypatch, entry.status_module, "run")
    entry.main(["status", "--watch", "--fix"])
    assert calls[0][1]["watch"] == 30


def test_status_report_with_explicit_path(monkeypatch):
    calls = _spy(monkeypatch, entry.status_module, "run")
    entry.main(["status", "--report", "/tmp/report.txt"])
    assert calls[0][1]["report"] is True
    assert calls[0][1]["report_path"] == "/tmp/report.txt"


def test_status_report_without_path_defaults_to_empty(monkeypatch):
    calls = _spy(monkeypatch, entry.status_module, "run")
    entry.main(["status", "--report"])
    assert calls[0][1]["report_path"] == ""


def test_status_report_followed_by_another_flag_leaves_path_empty(monkeypatch):
    calls = _spy(monkeypatch, entry.status_module, "run")
    entry.main(["status", "--report", "--fix"])
    assert calls[0][1]["report_path"] == ""


def test_status_fix_flag(monkeypatch):
    calls = _spy(monkeypatch, entry.status_module, "run")
    entry.main(["status", "--fix"])
    assert calls[0][1]["fix"] is True


# ── bundle ─────────────────────────────────────────────────────────────────────


def test_bundle_enable_with_name(monkeypatch):
    calls = _spy(monkeypatch, entry.bundles_module, "run")
    entry.main(["bundle", "enable", "monitoring"])
    assert calls == [(("enable", "monitoring"), {"stop_orphans": False})]


def test_bundle_disable_with_stop_orphans(monkeypatch):
    calls = _spy(monkeypatch, entry.bundles_module, "run")
    entry.main(["bundle", "disable", "voice", "--stop-orphans"])
    assert calls == [(("disable", "voice"), {"stop_orphans": True})]


def test_bundle_stop_orphans_flag_before_action_does_not_shift_positions(
    monkeypatch,
):
    calls = _spy(monkeypatch, entry.bundles_module, "run")
    entry.main(["bundle", "--stop-orphans", "disable", "voice"])
    assert calls == [(("disable", "voice"), {"stop_orphans": True})]


def test_bundle_status_no_name(monkeypatch):
    calls = _spy(monkeypatch, entry.bundles_module, "run")
    entry.main(["bundle", "status"])
    assert calls == [(("status", ""), {"stop_orphans": False})]


def test_bundle_no_action(monkeypatch):
    calls = _spy(monkeypatch, entry.bundles_module, "run")
    entry.main(["bundle"])
    assert calls == [(("", ""), {"stop_orphans": False})]


# ── install ────────────────────────────────────────────────────────────────────


def test_install_defaults_to_standard_profile(monkeypatch):
    calls = _spy(monkeypatch, entry.install_module, "run")
    entry.main([])
    assert calls == [(("standard",), {})]


def test_install_explicit_profile(monkeypatch):
    calls = _spy(monkeypatch, entry.install_module, "run")
    entry.main(["install", "--profile", "full"])
    assert calls == [(("full",), {})]


def test_install_unknown_profile_errors_without_dispatching(monkeypatch, capfd):
    calls = _spy(monkeypatch, entry.install_module, "run")

    rc = entry.main(["install", "--profile", "bogus"])

    out = capfd.readouterr().out
    assert rc == 1
    assert calls == []
    assert "Unknown install profile" in out


# ── unknown command ────────────────────────────────────────────────────────────


def test_unknown_command_errors_and_shows_help(monkeypatch, capfd):
    help_calls = _spy(monkeypatch, entry.help_module, "print_help")

    rc = entry.main(["not-a-real-verb"])

    out = capfd.readouterr().out
    assert rc == 1
    assert "Unknown command: not-a-real-verb" in out
    assert help_calls == [((), {})]


# ── _entry cleanup epilogue ────────────────────────────────────────────────────


def test_entry_calls_cleanup_with_normal_return_code(monkeypatch):
    monkeypatch.setattr(entry, "main", lambda argv: 3)
    cleanup_calls = []
    monkeypatch.setattr(entry.log, "cleanup", lambda code: cleanup_calls.append(code))

    rc = entry._entry([])

    assert rc == 3
    assert cleanup_calls == [3]


def test_entry_cleanup_on_system_exit_with_int_code(monkeypatch):
    def _raise(argv):
        raise SystemExit(2)

    monkeypatch.setattr(entry, "main", _raise)
    cleanup_calls = []
    monkeypatch.setattr(entry.log, "cleanup", lambda code: cleanup_calls.append(code))

    with pytest.raises(SystemExit):
        entry._entry([])

    assert cleanup_calls == [2]


def test_entry_cleanup_on_system_exit_with_none_code(monkeypatch):
    def _raise(argv):
        raise SystemExit()

    monkeypatch.setattr(entry, "main", _raise)
    cleanup_calls = []
    monkeypatch.setattr(entry.log, "cleanup", lambda code: cleanup_calls.append(code))

    with pytest.raises(SystemExit):
        entry._entry([])

    assert cleanup_calls == [0]


def test_entry_cleanup_on_system_exit_with_non_int_code(monkeypatch):
    def _raise(argv):
        raise SystemExit("boom")

    monkeypatch.setattr(entry, "main", _raise)
    cleanup_calls = []
    monkeypatch.setattr(entry.log, "cleanup", lambda code: cleanup_calls.append(code))

    with pytest.raises(SystemExit):
        entry._entry([])

    assert cleanup_calls == [1]


def test_entry_cleanup_on_other_exception_reraises(monkeypatch):
    def _raise(argv):
        raise RuntimeError("boom")

    monkeypatch.setattr(entry, "main", _raise)
    cleanup_calls = []
    monkeypatch.setattr(entry.log, "cleanup", lambda code: cleanup_calls.append(code))

    with pytest.raises(RuntimeError):
        entry._entry([])

    assert cleanup_calls == [1]
