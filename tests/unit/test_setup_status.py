"""Unit tests for the `status` verb (scripts/setup/status.py) -- previously
only verified structurally (container-name-set + headers) by
scripts/gate/status_verify.sh against a docker shim; the module's own
branches (ollama/tts-stt backend reporting, --fix, --report, --watch) had
zero direct unit tests (26%). subprocess/docker/health/env/time are all
mocked -- no real Docker calls, no real sleeping.
"""

from scripts.setup import status


class _FakeCompleted:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


# ── ollama backend probes ─────────────────────────────────────────────────────


def test_primary_reachable_true_on_zero_returncode(monkeypatch):
    monkeypatch.setattr(
        status.subprocess, "run", lambda argv, **kw: _FakeCompleted(returncode=0)
    )
    assert status._primary_reachable("gpu-node:11434") is True


def test_primary_reachable_false_on_nonzero_returncode(monkeypatch):
    monkeypatch.setattr(
        status.subprocess, "run", lambda argv, **kw: _FakeCompleted(returncode=1)
    )
    assert status._primary_reachable("gpu-node:11434") is False


def test_primary_reachable_false_on_oserror(monkeypatch):
    def _raise(argv, **kw):
        raise OSError("docker not found")

    monkeypatch.setattr(status.subprocess, "run", _raise)
    assert status._primary_reachable("gpu-node:11434") is False


def test_fallback_alive_false_when_container_not_running(monkeypatch):
    monkeypatch.setattr(status.docker, "container_running", lambda svc: False)
    monkeypatch.setattr(
        status.docker, "cmd_ok", lambda argv: (_ for _ in ()).throw(AssertionError)
    )
    assert status._fallback_alive() is False


def test_fallback_alive_true_when_running_and_cmd_ok(monkeypatch):
    monkeypatch.setattr(status.docker, "container_running", lambda svc: True)
    monkeypatch.setattr(status.docker, "cmd_ok", lambda argv: True)
    assert status._fallback_alive() is True


def test_fallback_alive_false_when_running_but_cmd_fails(monkeypatch):
    monkeypatch.setattr(status.docker, "container_running", lambda svc: True)
    monkeypatch.setattr(status.docker, "cmd_ok", lambda argv: False)
    assert status._fallback_alive() is False


# ── _print_ollama_backend ─────────────────────────────────────────────────────


def test_print_ollama_backend_internal_when_nothing_set(monkeypatch, capfd):
    monkeypatch.setattr(status.env, "get", lambda key: "")
    status._print_ollama_backend()
    out = capfd.readouterr().out
    assert "internal — platform-managed container" in out


def test_print_ollama_backend_external_when_base_set(monkeypatch, capfd):
    monkeypatch.setattr(
        status.env,
        "get",
        lambda key: "http://host.docker.internal:11434"
        if key == "OLLAMA_BASE_URL"
        else "",
    )
    status._print_ollama_backend()
    out = capfd.readouterr().out
    assert "external — http://host.docker.internal:11434" in out


def test_print_ollama_backend_failover_reachable_no_warning(monkeypatch, capfd):
    monkeypatch.setattr(
        status.env,
        "get",
        lambda key: "gpu-node:11434" if key == "OLLAMA_FAILOVER_PRIMARY" else "",
    )
    monkeypatch.setattr(status, "_primary_reachable", lambda hostport: True)
    monkeypatch.setattr(status, "_fallback_alive", lambda: True)

    status._print_ollama_backend()

    out = capfd.readouterr().out
    assert "REACHABLE" in out
    assert "serving from the external primary" in out
    assert "not responding" not in out


def test_print_ollama_backend_failover_unreachable_warns_on_dead_fallback(
    monkeypatch, capfd
):
    monkeypatch.setattr(
        status.env,
        "get",
        lambda key: "gpu-node:11434" if key == "OLLAMA_FAILOVER_PRIMARY" else "",
    )
    monkeypatch.setattr(status, "_primary_reachable", lambda hostport: False)
    monkeypatch.setattr(status, "_fallback_alive", lambda: False)

    status._print_ollama_backend()

    out = capfd.readouterr().out
    assert "UNREACHABLE" in out
    assert "serving from the internal fallback" in out
    assert "not responding" in out


# ── tts-stt backend probes (mirrors ollama) ───────────────────────────────────


def test_tts_stt_primary_reachable_true_on_zero_returncode(monkeypatch):
    monkeypatch.setattr(
        status.subprocess, "run", lambda argv, **kw: _FakeCompleted(returncode=0)
    )
    assert status._tts_stt_primary_reachable("gpu-node:8006") is True


def test_tts_stt_primary_reachable_false_on_oserror(monkeypatch):
    def _raise(argv, **kw):
        raise OSError("boom")

    monkeypatch.setattr(status.subprocess, "run", _raise)
    assert status._tts_stt_primary_reachable("gpu-node:8006") is False


def test_tts_stt_fallback_alive_false_when_not_running(monkeypatch):
    monkeypatch.setattr(status.docker, "container_running", lambda svc: False)
    assert status._tts_stt_fallback_alive() is False


def test_tts_stt_fallback_alive_true_when_running_and_healthy(monkeypatch):
    monkeypatch.setattr(status.docker, "container_running", lambda svc: True)
    monkeypatch.setattr(status.docker, "cmd_ok", lambda argv: True)
    assert status._tts_stt_fallback_alive() is True


def test_print_tts_stt_backend_internal_when_nothing_set(monkeypatch, capfd):
    monkeypatch.setattr(status.env, "get", lambda key: "")
    status._print_tts_stt_backend()
    out = capfd.readouterr().out
    assert "internal — platform-managed container" in out


def test_print_tts_stt_backend_external_when_base_set(monkeypatch, capfd):
    monkeypatch.setattr(
        status.env,
        "get",
        lambda key: "http://host.docker.internal:8006"
        if key == "TTS_STT_BASE_URL"
        else "",
    )
    status._print_tts_stt_backend()
    out = capfd.readouterr().out
    assert "external — http://host.docker.internal:8006" in out


def test_print_tts_stt_backend_failover_reachable_no_warning(monkeypatch, capfd):
    monkeypatch.setattr(
        status.env,
        "get",
        lambda key: "gpu-node:8006" if key == "TTS_STT_FAILOVER_PRIMARY" else "",
    )
    monkeypatch.setattr(status, "_tts_stt_primary_reachable", lambda hostport: True)
    monkeypatch.setattr(status, "_tts_stt_fallback_alive", lambda: True)

    status._print_tts_stt_backend()

    out = capfd.readouterr().out
    assert "REACHABLE" in out
    assert "serving from the external primary" in out
    assert "not responding" not in out


def test_print_tts_stt_backend_failover_unreachable_warns_on_dead_fallback(
    monkeypatch, capfd
):
    monkeypatch.setattr(
        status.env,
        "get",
        lambda key: "gpu-node:8006" if key == "TTS_STT_FAILOVER_PRIMARY" else "",
    )
    monkeypatch.setattr(status, "_tts_stt_primary_reachable", lambda hostport: False)
    monkeypatch.setattr(status, "_tts_stt_fallback_alive", lambda: False)

    status._print_tts_stt_backend()

    out = capfd.readouterr().out
    assert "UNREACHABLE" in out
    assert "not responding" in out


# ── _count / _filtered ────────────────────────────────────────────────────────


def test_count_counts_only_minder_prefixed_lines(monkeypatch):
    monkeypatch.setattr(
        status.subprocess,
        "run",
        lambda argv, **kw: _FakeCompleted(
            stdout="minder-api-gateway\nother-thing\nminder-postgres\n"
        ),
    )
    assert status._count([]) == 2


def test_count_returns_zero_on_oserror(monkeypatch):
    def _raise(argv, **kw):
        raise OSError("boom")

    monkeypatch.setattr(status.subprocess, "run", _raise)
    assert status._count([]) == 0


def test_filtered_keeps_header_and_prefixed_lines(monkeypatch):
    monkeypatch.setattr(
        status.subprocess,
        "run",
        lambda argv, **kw: _FakeCompleted(
            stdout="NAMES  STATUS\nminder-api-gateway  Up\nother-thing  Up\n"
        ),
    )
    result = status._filtered(["docker", "ps"], "NAMES")
    assert result == ["NAMES  STATUS", "minder-api-gateway  Up"]


def test_filtered_returns_empty_on_oserror(monkeypatch):
    def _raise(argv, **kw):
        raise OSError("boom")

    monkeypatch.setattr(status.subprocess, "run", _raise)
    assert status._filtered(["docker", "ps"], "NAMES") == []


# ── _print_status ──────────────────────────────────────────────────────────────


def test_print_status_renders_summary_containers_stats_and_backends(monkeypatch, capfd):
    monkeypatch.setattr(status, "_count", lambda filter_args: 3)
    monkeypatch.setattr(
        status,
        "_filtered",
        lambda argv, token: ["NAMES", "minder-api-gateway  Up (healthy)"],
    )
    monkeypatch.setattr(status, "_print_ollama_backend", lambda: None)
    monkeypatch.setattr(status, "_print_tts_stt_backend", lambda: None)
    calls = []
    monkeypatch.setattr(status.health, "run_health_checks", lambda: calls.append(1))

    status._print_status()

    out = capfd.readouterr().out
    assert "Minder Platform Status" in out
    assert "total=3" in out
    assert "minder-api-gateway" in out
    assert calls == [1]


def test_print_status_summary_uses_color_when_colors_on(monkeypatch, capfd):
    monkeypatch.setattr(status, "_count", lambda filter_args: 1)
    monkeypatch.setattr(status, "_filtered", lambda argv, token: [])
    monkeypatch.setattr(status, "_print_ollama_backend", lambda: None)
    monkeypatch.setattr(status, "_print_tts_stt_backend", lambda: None)
    monkeypatch.setattr(status.health, "run_health_checks", lambda: None)
    monkeypatch.setattr(status.log, "_colors_on", lambda: True)

    status._print_status()

    out = capfd.readouterr().out
    assert status.log._BOLD in out
    assert "total=1" in out


def test_print_status_truncates_container_table_to_30_lines(monkeypatch, capfd):
    monkeypatch.setattr(status, "_count", lambda filter_args: 0)
    long_table = [f"minder-svc-{i}" for i in range(50)]
    monkeypatch.setattr(
        status,
        "_filtered",
        lambda argv, token: long_table if "ps" in argv else [],
    )
    monkeypatch.setattr(status, "_print_ollama_backend", lambda: None)
    monkeypatch.setattr(status, "_print_tts_stt_backend", lambda: None)
    monkeypatch.setattr(status.health, "run_health_checks", lambda: None)

    status._print_status()

    out = capfd.readouterr().out
    assert "minder-svc-29" in out
    assert "minder-svc-30" not in out


# ── _unhealthy_or_stopped / _fix_unhealthy ────────────────────────────────────


def test_unhealthy_or_stopped_dedupes_across_specs(monkeypatch):
    def _fake_run(argv, **kw):
        if any("unhealthy" in a for a in argv):
            return _FakeCompleted(stdout="minder-rag-pipeline\n")
        if any("exited" in a for a in argv):
            return _FakeCompleted(stdout="minder-rag-pipeline\nminder-marketplace\n")
        return _FakeCompleted(stdout="other-thing\n")

    monkeypatch.setattr(status.subprocess, "run", _fake_run)

    result = status._unhealthy_or_stopped()

    assert result == ["minder-rag-pipeline", "minder-marketplace"]


def test_unhealthy_or_stopped_tolerates_one_spec_failing(monkeypatch):
    def _fake_run(argv, **kw):
        if any("unhealthy" in a for a in argv):
            raise OSError("boom")
        if any("exited" in a for a in argv):
            return _FakeCompleted(stdout="minder-rag-pipeline\n")
        return _FakeCompleted(stdout="")

    monkeypatch.setattr(status.subprocess, "run", _fake_run)

    assert status._unhealthy_or_stopped() == ["minder-rag-pipeline"]


def test_fix_unhealthy_reports_nothing_to_fix(monkeypatch, capfd):
    monkeypatch.setattr(status, "_unhealthy_or_stopped", lambda: [])
    monkeypatch.setattr(
        status.docker, "run", lambda *a: (_ for _ in ()).throw(AssertionError)
    )

    status._fix_unhealthy()

    assert "nothing to fix" in capfd.readouterr().out


def test_fix_unhealthy_restarts_each_target(monkeypatch, capfd):
    monkeypatch.setattr(
        status, "_unhealthy_or_stopped", lambda: ["minder-a", "minder-b"]
    )

    def _fake_run(*args):
        return 0 if args[-1] == "minder-a" else 1

    monkeypatch.setattr(status.docker, "run", _fake_run)

    status._fix_unhealthy()

    out = capfd.readouterr().out
    assert "restarted minder-a" in out
    assert "failed to restart minder-b" in out


# ── _write_report ──────────────────────────────────────────────────────────────


def test_write_report_uses_explicit_path(monkeypatch, tmp_path):
    monkeypatch.setattr(status, "_count", lambda filter_args: 1)
    monkeypatch.setattr(status, "_filtered", lambda argv, token: ["minder-x"])
    monkeypatch.setattr(status.docker, "capture", lambda argv: "bridge\n")
    out_file = tmp_path / "report.txt"

    rc = status._write_report(str(out_file))

    assert rc == 0
    content = out_file.read_text(encoding="utf-8")
    assert "Minder health report" in content
    assert "[Summary]" in content
    assert "total=1" in content
    assert "[Network]" in content
    assert "bridge" in content


def test_write_report_defaults_to_logs_dir_with_timestamped_name(monkeypatch, tmp_path):
    monkeypatch.setattr(status, "_count", lambda filter_args: 0)
    monkeypatch.setattr(status, "_filtered", lambda argv, token: [])
    monkeypatch.setattr(status.docker, "capture", lambda argv: "")
    monkeypatch.setattr(status.config, "LOGS_DIR", tmp_path / "logs")

    rc = status._write_report("")

    assert rc == 0
    written = list((tmp_path / "logs").glob("health-report-*.txt"))
    assert len(written) == 1


def test_write_report_returns_1_on_write_failure(monkeypatch, capfd):
    monkeypatch.setattr(status, "_count", lambda filter_args: 0)
    monkeypatch.setattr(status, "_filtered", lambda argv, token: [])
    monkeypatch.setattr(status.docker, "capture", lambda argv: "")

    def _raise_open(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(status, "open", _raise_open, raising=False)

    rc = status._write_report("/some/path.txt")

    assert rc == 1
    assert "Failed to write report" in capfd.readouterr().out


# ── _watch ───────────────────────────────────────────────────────────────────


def test_watch_renders_and_sleeps_until_interrupted(monkeypatch):
    calls = []
    monkeypatch.setattr(status, "_print_status", lambda: calls.append("render"))

    def _fake_sleep(secs):
        calls.append(("sleep", secs))
        raise KeyboardInterrupt

    monkeypatch.setattr(status.time, "sleep", _fake_sleep)
    monkeypatch.setattr(status.log, "_colors_on", lambda: False)

    rc = status._watch(15)

    assert rc == 0
    assert calls == ["render", ("sleep", 15)]


def test_watch_clears_screen_when_colors_on(monkeypatch, capfd):
    monkeypatch.setattr(status, "_print_status", lambda: None)

    def _fake_sleep(secs):
        raise KeyboardInterrupt

    monkeypatch.setattr(status.time, "sleep", _fake_sleep)
    monkeypatch.setattr(status.log, "_colors_on", lambda: True)

    status._watch(5)

    out = capfd.readouterr().out
    assert "\033[2J\033[H" in out


# ── run() dispatch ─────────────────────────────────────────────────────────────


def test_run_json_mode_only_calls_health_checks(monkeypatch):
    calls = []
    monkeypatch.setattr(
        status.health,
        "run_health_checks",
        lambda json_mode=False: calls.append(json_mode),
    )
    monkeypatch.setattr(
        status, "_print_status", lambda: (_ for _ in ()).throw(AssertionError)
    )

    rc = status.run(json_mode=True)

    assert rc == 0
    assert calls == [True]


def test_run_fix_then_falls_through_to_print_status(monkeypatch):
    calls = []
    monkeypatch.setattr(status, "_fix_unhealthy", lambda: calls.append("fix"))
    monkeypatch.setattr(status, "_print_status", lambda: calls.append("print"))

    rc = status.run(fix=True)

    assert rc == 0
    assert calls == ["fix", "print"]


def test_run_report_returns_write_report_result_without_printing_status(monkeypatch):
    monkeypatch.setattr(status, "_write_report", lambda path: 0)
    monkeypatch.setattr(
        status, "_print_status", lambda: (_ for _ in ()).throw(AssertionError)
    )

    rc = status.run(report=True, report_path="/tmp/x.txt")

    assert rc == 0


def test_run_watch_returns_watch_result_without_printing_status(monkeypatch):
    monkeypatch.setattr(status, "_watch", lambda interval: 0)
    monkeypatch.setattr(
        status, "_print_status", lambda: (_ for _ in ()).throw(AssertionError)
    )

    rc = status.run(watch=30)

    assert rc == 0


def test_run_default_prints_status(monkeypatch):
    calls = []
    monkeypatch.setattr(status, "_print_status", lambda: calls.append("print"))

    rc = status.run()

    assert rc == 0
    assert calls == ["print"]
