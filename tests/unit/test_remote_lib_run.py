"""Regression test for remote_lib.run()'s stdout streaming.

paramiko's ChannelFile.readline() decodes in *strict* utf-8 with no errors=
knob (its internal `u()` helper). A remote PowerShell command whose output
contains a Windows-1252 byte (e.g. a curly quote 0x93/0x94/0x92, common in
PowerShell's own error/table formatting) crashed the whole SSH call with
UnicodeDecodeError before a single line printed. Confirmed live against
hantal: `ConvertTo-Json`'d PowerShell output containing a curly quote raised
`UnicodeDecodeError: 'utf-8' codec can't decode byte 0x94 ...` from
`paramiko/file.py:readline`.

No real SSH connection: `client.exec_command` and its returned channel are
stubbed.

`remote_lib` imports `paramiko` at module level -- a personal dev-workflow
dependency, deliberately not in src/requirements/*.txt, so CI's Unit Tests
job doesn't have it installed (see test_remote_ssh_arg_parsing.py). Skip
cleanly there instead of erroring.
"""

import types

import pytest

pytest.importorskip("paramiko")

from scripts.dev import remote_lib  # noqa: E402


class _FakeChannel:
    def __init__(self, chunks, exit_status=0):
        self._buffer = b"".join(chunks)
        self._exit_status = exit_status

    def makefile(self, mode):
        assert mode == "rb"
        return _FakeBinaryFile(self._buffer)

    def recv_exit_status(self):
        return self._exit_status


class _FakeBinaryFile:
    def __init__(self, data):
        self._lines = data.splitlines(keepends=True)
        self._idx = 0

    def readline(self):
        if self._idx >= len(self._lines):
            return b""
        line = self._lines[self._idx]
        self._idx += 1
        return line


class _FakeChannelFile:
    def __init__(self, channel):
        self.channel = channel


class _FakeStderr:
    def __init__(self, data=b""):
        self._data = data

    def read(self):
        return self._data


def _stub_client(monkeypatch, chunks, exit_status=0, stderr_data=b""):
    channel = _FakeChannel(chunks, exit_status)
    stdout = _FakeChannelFile(channel)
    stderr = _FakeStderr(stderr_data)

    fake_client = types.SimpleNamespace(
        exec_command=lambda *a, **k: (None, stdout, stderr),
        close=lambda: None,
    )
    monkeypatch.setattr(
        remote_lib,
        "connect",
        lambda alias: (fake_client, {"get_pty": False}, {}),
    )
    monkeypatch.setattr(remote_lib, "build_command", lambda *a, **k: "irrelevant")


def test_run_survives_non_utf8_byte_in_output(monkeypatch, capsys):
    """A stray Windows-1252 byte (0x94, a right curly quote) must not crash the
    whole SSH call -- it should be replaced, not raised."""
    _stub_client(monkeypatch, [b"before \x94 after\n", b"second line\n"])

    rc = remote_lib.run("hantal", ["Get-Something"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "before" in out and "after" in out
    assert "second line" in out


def test_run_streams_plain_ascii_output(monkeypatch, capsys):
    _stub_client(monkeypatch, [b"line one\n", b"line two\n"], exit_status=0)

    rc = remote_lib.run("hantal", ["echo hi"])

    assert rc == 0
    out = capsys.readouterr().out
    assert out == "line one\nline two\n"


def test_run_prints_non_empty_stderr_after_stdout(monkeypatch, capsys):
    _stub_client(
        monkeypatch,
        [b"line one\n"],
        exit_status=1,
        stderr_data=b"something went wrong\n",
    )

    rc = remote_lib.run("hantal", ["exit 1"])

    assert rc == 1
    out = capsys.readouterr().out
    assert "line one" in out
    assert "something went wrong" in out


def test_run_skips_blank_stderr(monkeypatch, capsys):
    _stub_client(monkeypatch, [b"line one\n"], exit_status=0, stderr_data=b"   \n")

    remote_lib.run("hantal", ["echo hi"])

    out = capsys.readouterr().out
    assert out == "line one\n"
