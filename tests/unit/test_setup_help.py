"""Unit tests for scripts/setup/help.py -- render(), print_help(), and
print_success_banner() had zero direct coverage (11%). log._emit writes to
sys.stdout.buffer, so capfd (not capsys) is used, matching the established
convention in test_setup_doctor_run.py.
"""

import io

import pytest

from scripts.setup import help as help_mod


def test_render_without_color_has_no_ansi_and_includes_version_and_script():
    text = help_mod.render(color=False)
    assert "\033[" not in text
    assert help_mod.config.SCRIPT_VERSION in text
    assert help_mod.config.SCRIPT_NAME in text
    assert "USAGE" in text
    assert "BUNDLES" in text


def test_render_with_color_wraps_bold_markers_in_ansi():
    text = help_mod.render(color=True)
    assert "\033[1m" in text
    assert "\033[0m" in text


def test_print_help_writes_utf8_bytes_via_stdout_buffer(monkeypatch, capfd):
    monkeypatch.setattr(help_mod.sys.stdout, "isatty", lambda: False)
    help_mod.print_help()
    out = capfd.readouterr().out
    assert "Minder Platform" in out
    assert help_mod.config.SCRIPT_VERSION in out


def test_print_help_uses_color_when_stdout_is_a_tty(monkeypatch, capfd):
    monkeypatch.setattr(help_mod.sys.stdout, "isatty", lambda: True)
    help_mod.print_help()
    out = capfd.readouterr().out
    assert "\033[1m" in out


def test_print_help_falls_back_to_text_write_without_a_binary_buffer(monkeypatch):
    class _NoBufferStream(io.StringIO):
        def isatty(self):
            return False

    fake_stdout = _NoBufferStream()
    monkeypatch.setattr(help_mod.sys, "stdout", fake_stdout)
    help_mod.print_help()
    written = fake_stdout.getvalue()
    assert "Minder Platform" in written


@pytest.fixture
def no_color(monkeypatch):
    monkeypatch.setattr(help_mod.log, "_colors_on", lambda: False)


def test_print_success_banner_default_hides_ai_and_monitoring_sections(
    monkeypatch, no_color, capfd
):
    monkeypatch.setattr(help_mod.bundles, "is_enabled", lambda name: False)
    help_mod.print_success_banner()
    out = capfd.readouterr().out
    assert "AI Services" not in out
    assert "Monitoring bundle is OFF" in out
    assert "bundle enable monitoring" in out
    assert "http://localhost:9090" not in out


def test_print_success_banner_chat_enabled_shows_chat_section(
    monkeypatch, no_color, capfd
):
    monkeypatch.setattr(help_mod.bundles, "is_enabled", lambda name: name == "chat")
    help_mod.print_success_banner()
    out = capfd.readouterr().out
    assert "AI Services" in out
    assert "OpenWebUI" in out
    assert "chat.minder.local" in out
    assert "TTS / STT" not in out


def test_print_success_banner_voice_enabled_shows_voice_section(
    monkeypatch, no_color, capfd
):
    monkeypatch.setattr(help_mod.bundles, "is_enabled", lambda name: name == "voice")
    help_mod.print_success_banner()
    out = capfd.readouterr().out
    assert "AI Services" in out
    assert "TTS / STT" in out
    assert "tts-stt-mode external|failover" in out
    assert "OpenWebUI           " not in out


def test_print_success_banner_monitoring_enabled_shows_dashboards(
    monkeypatch, no_color, capfd
):
    monkeypatch.setattr(
        help_mod.bundles, "is_enabled", lambda name: name == "monitoring"
    )
    help_mod.print_success_banner()
    out = capfd.readouterr().out
    assert "Prometheus" in out
    assert "Grafana" in out
    assert "InfluxDB" in out
    assert "Monitoring bundle is OFF" not in out


def test_print_success_banner_always_shows_core_apis_and_commands(
    monkeypatch, no_color, capfd
):
    monkeypatch.setattr(help_mod.bundles, "is_enabled", lambda name: False)
    help_mod.print_success_banner()
    out = capfd.readouterr().out
    for name, port in help_mod._API_BANNER:
        assert name in out
        assert str(port) in out
    for cmd, desc in help_mod._COMMANDS_BANNER:
        assert desc in out
    assert str(help_mod.config.LOG_FILE) in out


def test_print_success_banner_uses_color_codes_when_a_tty(monkeypatch, capfd):
    monkeypatch.setattr(help_mod.log, "_colors_on", lambda: True)
    monkeypatch.setattr(help_mod.bundles, "is_enabled", lambda name: False)
    help_mod.print_success_banner()
    out = capfd.readouterr().out
    assert "\033[1m" in out
