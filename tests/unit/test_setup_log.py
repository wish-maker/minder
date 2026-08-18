"""Unit tests for scripts/setup/log.py -- the console-logging module itself
had zero direct unit tests (79%); every other test file only ever
monkeypatches pieces of it as a caller. capfd (not capsys) throughout since
_emit/_write_raw write to sys.stdout.buffer directly. config.LOG_FILE is
always redirected to a tmp_path file so no test ever touches the real
logs/ directory.
"""

import re
import threading

import pytest

from scripts.setup import log


@pytest.fixture(autouse=True)
def _log_file(tmp_path, monkeypatch):
    monkeypatch.setattr(log.config, "LOG_FILE", tmp_path / "setup-test.log")


@pytest.fixture(autouse=True)
def _no_color(monkeypatch):
    monkeypatch.setattr(log, "_colors_on", lambda: False)


# ── _colors_on ─────────────────────────────────────────────────────────────────


def test_colors_on_reflects_stdout_isatty(monkeypatch):
    monkeypatch.undo()  # remove the autouse _no_color patch for this test only
    monkeypatch.setattr(log.sys.stdout, "isatty", lambda: True)
    assert log._colors_on() is True
    monkeypatch.setattr(log.sys.stdout, "isatty", lambda: False)
    assert log._colors_on() is False


# ── _emit / _write_raw ─────────────────────────────────────────────────────────


def test_emit_writes_utf8_with_trailing_newline(capfd):
    log._emit("hello → world")
    assert capfd.readouterr().out == "hello → world\n"


def test_emit_falls_back_to_text_write_without_a_binary_buffer(monkeypatch):
    import io

    class _NoBuffer(io.StringIO):
        pass

    fake_stdout = _NoBuffer()
    monkeypatch.setattr(log.sys, "stdout", fake_stdout)
    log._emit("plain text")
    assert fake_stdout.getvalue() == "plain text\n"


def test_write_raw_writes_without_trailing_newline(capfd):
    log._write_raw("no newline here")
    assert capfd.readouterr().out == "no newline here"


def test_write_raw_falls_back_to_text_write_without_a_binary_buffer(monkeypatch):
    import io

    class _NoBuffer(io.StringIO):
        pass

    fake_stdout = _NoBuffer()
    monkeypatch.setattr(log.sys, "stdout", fake_stdout)
    log._write_raw("raw")
    assert fake_stdout.getvalue() == "raw"


# ── _now / _strip_ansi ─────────────────────────────────────────────────────────


def test_now_matches_hh_mm_ss():
    assert re.fullmatch(r"\d{2}:\d{2}:\d{2}", log._now())


def test_strip_ansi_removes_color_codes():
    colored = f"{log._RED}error{log._NC}"
    assert log._strip_ansi(colored) == "error"


def test_strip_ansi_leaves_plain_text_untouched():
    assert log._strip_ansi("no codes here") == "no codes here"


# ── _append_file ───────────────────────────────────────────────────────────────


def test_append_file_writes_a_line(tmp_path):
    log._append_file("a log line")
    assert log.config.LOG_FILE.read_text(encoding="utf-8") == "a log line\n"


def test_append_file_appends_across_multiple_calls():
    log._append_file("first")
    log._append_file("second")
    assert log.config.LOG_FILE.read_text(encoding="utf-8") == "first\nsecond\n"


def test_append_file_tolerates_oserror(monkeypatch, tmp_path):
    monkeypatch.setattr(log.config, "LOG_FILE", tmp_path / "no-such-dir" / "x.log")
    log._append_file("swallowed")  # must not raise


# ── _line ──────────────────────────────────────────────────────────────────────


def test_line_plain_when_colors_off():
    line = log._line("i", "HEAD", "MSG", "hello", "12:00:00")
    assert "HEAD" not in line
    assert "MSG" not in line
    assert "hello" in line
    assert "12:00:00" in line


def test_line_wraps_head_and_body_in_color_when_on(monkeypatch):
    monkeypatch.setattr(log, "_colors_on", lambda: True)
    line = log._line("i", log._GREEN, log._GREEN, "hello", "12:00:00")
    assert log._GREEN in line
    assert log._DIM in line
    assert log._NC in line


def test_line_leaves_body_unwrapped_when_msg_color_is_empty(monkeypatch):
    monkeypatch.setattr(log, "_colors_on", lambda: True)
    line = log._line("i", log._BLUE, "", "hello", "12:00:00")
    # body isn't wrapped in msg_color when msg_color is falsy (info()'s case)
    assert line.count(log._NC) == 2  # head's NC + the trailing reset from _line's tail


# ── info / success / warn / error / debug / detail ────────────────────────────


def test_info_emits_and_appends(capfd):
    log.info("informational")
    out = capfd.readouterr().out
    assert "informational" in out
    assert "[INFO] informational" in log.config.LOG_FILE.read_text(encoding="utf-8")


def test_success_emits_and_appends(capfd):
    log.success("it worked")
    out = capfd.readouterr().out
    assert "it worked" in out
    assert "[OK] it worked" in log.config.LOG_FILE.read_text(encoding="utf-8")


def test_warn_emits_and_appends(capfd):
    log.warn("careful")
    assert "[WARN] careful" in log.config.LOG_FILE.read_text(encoding="utf-8")


def test_error_emits_and_appends(capfd):
    log.error("boom")
    assert "[ERROR] boom" in log.config.LOG_FILE.read_text(encoding="utf-8")


def test_error_file_line_strips_ansi_even_if_message_has_color_codes():
    colored_msg = f"{log._RED}already colored{log._NC}"
    log.error(colored_msg)
    content = log.config.LOG_FILE.read_text(encoding="utf-8")
    assert "\033[" not in content
    assert "already colored" in content


def test_debug_noop_when_verbose_off(monkeypatch, capfd):
    monkeypatch.setattr(log.config, "VERBOSE", False)
    log.debug("hidden")
    assert capfd.readouterr().out == ""
    assert not log.config.LOG_FILE.exists()


def test_debug_emits_when_verbose_on(monkeypatch, capfd):
    monkeypatch.setattr(log.config, "VERBOSE", True)
    log.debug("shown")
    out = capfd.readouterr().out
    assert "shown" in out
    assert "[DEBUG] shown" in log.config.LOG_FILE.read_text(encoding="utf-8")


def test_detail_indents_and_does_not_append_to_log_file(capfd):
    log.detail("a detail line")
    out = capfd.readouterr().out
    assert out == "  a detail line\n"
    assert not log.config.LOG_FILE.exists()


def test_detail_wraps_in_dim_color_when_on(monkeypatch, capfd):
    monkeypatch.setattr(log, "_colors_on", lambda: True)
    log.detail("a detail line")
    out = capfd.readouterr().out
    assert log._DIM in out


# ── bold / step ────────────────────────────────────────────────────────────────


def test_bold_plain_when_colors_off():
    assert log.bold("Title") == "Title"


def test_bold_wraps_when_colors_on(monkeypatch):
    monkeypatch.setattr(log, "_colors_on", lambda: True)
    result = log.bold("Title")
    assert result == f"{log._BOLD}Title{log._NC}"


def test_step_emits_leading_blank_line_and_appends_step_marker(capfd):
    log.step("Doing a thing")
    out = capfd.readouterr().out
    assert out == "\n▸ Doing a thing\n"
    assert log.config.LOG_FILE.read_text(encoding="utf-8") == "[STEP] Doing a thing\n"


def test_step_bold_cyan_when_colors_on(monkeypatch, capfd):
    monkeypatch.setattr(log, "_colors_on", lambda: True)
    log.step("Doing a thing")
    out = capfd.readouterr().out
    assert log._BOLD in out
    assert log._CYAN in out


# ── cleanup ────────────────────────────────────────────────────────────────────


def test_cleanup_zero_exit_stays_silent(capfd):
    # cleanup() always stops the spinner (clear-line sequence); "silent" means
    # no "exited unexpectedly" epilogue on a clean exit.
    log.cleanup(0)
    out = capfd.readouterr().out
    assert "exited unexpectedly" not in out


def test_cleanup_nonzero_exit_prints_epilogue(capfd):
    log.cleanup(1)
    out = capfd.readouterr().out
    assert "exited unexpectedly (code 1)" in out
    assert "Full log:" in out


def test_cleanup_nonzero_exit_with_color_on(monkeypatch, capfd):
    monkeypatch.setattr(log, "_colors_on", lambda: True)
    log.cleanup(2)
    out = capfd.readouterr().out
    assert log._RED in out
    assert log._DIM in out


def test_cleanup_always_stops_the_spinner(monkeypatch):
    calls = []
    monkeypatch.setattr(log, "spinner_stop", lambda: calls.append(1))
    log.cleanup(0)
    assert calls == [1]


# ── spinner_start / spinner_stop ───────────────────────────────────────────────


def test_spinner_start_then_stop_leaves_a_clean_line(capfd):
    log.spinner_start("Working…")
    log.spinner_stop()
    out = capfd.readouterr().out
    assert out.endswith("\r\033[K")
    assert log._spinner_thread is None


def test_spinner_stop_without_a_running_spinner_is_a_noop(capfd):
    log.spinner_stop()
    assert capfd.readouterr().out == "\r\033[K"


def test_spinner_start_replaces_a_previous_spinner(capfd):
    log.spinner_start("First…")
    first_thread = log._spinner_thread
    log.spinner_start("Second…")
    assert log._spinner_thread is not first_thread
    assert not first_thread.is_alive()
    log.spinner_stop()


def test_spinner_produces_colored_frame_output_when_colors_on(monkeypatch):
    monkeypatch.setattr(log, "_colors_on", lambda: True)
    ready = threading.Event()
    captured = []

    real_write_raw = log._write_raw

    def _tracking_write_raw(text):
        captured.append(text)
        ready.set()
        real_write_raw(text)

    import unittest.mock

    with unittest.mock.patch.object(log, "_write_raw", _tracking_write_raw):
        log.spinner_start("Spinning…")
        assert ready.wait(timeout=2)
        log.spinner_stop()

    assert any(log._CYAN in text for text in captured)


def test_spinner_produces_frame_output_while_running():
    ready = threading.Event()

    real_write_raw = log._write_raw

    def _tracking_write_raw(text):
        ready.set()
        real_write_raw(text)

    import unittest.mock

    with unittest.mock.patch.object(log, "_write_raw", _tracking_write_raw):
        log.spinner_start("Spinning…")
        assert ready.wait(timeout=2)
        log.spinner_stop()


# ── progress_init / progress_next ─────────────────────────────────────────────


def test_progress_init_resets_step_counter():
    log.progress_init(4)
    assert log._progress_total == 4
    assert log._progress_step == 0


def test_progress_next_renders_step_and_percent(capfd):
    log.progress_init(4)
    log.progress_next("Step one")
    out = capfd.readouterr().out
    assert "[1/4] Step one" in out
    assert "25%" in out
    assert "█" * 5 in out


def test_progress_next_advances_across_calls(capfd):
    log.progress_init(2)
    log.progress_next("Step one")
    capfd.readouterr()
    log.progress_next("Step two")
    out = capfd.readouterr().out
    assert "[2/2] Step two" in out
    assert "100%" in out
    assert "█" * 20 in out


def test_progress_next_with_color_on(monkeypatch, capfd):
    monkeypatch.setattr(log, "_colors_on", lambda: True)
    log.progress_init(1)
    log.progress_next("Only step")
    out = capfd.readouterr().out
    assert log._CYAN in out
    assert log._BOLD in out


# ── section ────────────────────────────────────────────────────────────────────


def test_section_draws_a_box_with_the_title(capfd):
    log.section("My Title")
    out = capfd.readouterr().out
    assert "┌" + "─" * 50 + "┐" in out
    assert "My Title" in out
    assert "└" + "─" * 50 + "┘" in out


def test_section_pads_to_48_bytes_not_48_code_points(capfd):
    # A multibyte title (each emoji is 4 UTF-8 bytes) must get fewer trailing
    # spaces than a naive code-point-width pad would produce.
    log.section("🩺  Diagnostics")
    out = capfd.readouterr().out
    title_line = [ln for ln in out.splitlines() if "Diagnostics" in ln][0]
    # "│  " + title + padding + "│" -- confirm the closing bar is present and
    # the padding was computed against the UTF-8 byte length.
    title = "🩺  Diagnostics"
    expected_pad = max(0, 48 - len(title.encode("utf-8")))
    assert title_line == f"│  {title}{' ' * expected_pad}│"


def test_section_color_on(monkeypatch, capfd):
    monkeypatch.setattr(log, "_colors_on", lambda: True)
    log.section("Title")
    out = capfd.readouterr().out
    assert log._MAGENTA in out
    assert log._BOLD in out
