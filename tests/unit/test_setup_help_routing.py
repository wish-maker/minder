"""Unit tests for `<verb> --help` routing in the setup CLI (#234 item 5).

The bug: help was only shown when the FIRST positional was help/-h/--help, so
`setup.sh status --help` fell through and RAN `status`. `-h`/`--help` anywhere in
argv must route to help instead of executing the verb.

No Docker: help is a pure print; we stub print_help and assert the verb module is
never reached.
"""

import pytest

from scripts.setup import __main__ as entry


@pytest.fixture
def spy(monkeypatch):
    """Record whether help printed and whether `status` ran."""
    seen = {"help": 0, "status": 0}
    monkeypatch.setattr(
        entry.help_module,
        "print_help",
        lambda: seen.__setitem__("help", seen["help"] + 1),
    )
    monkeypatch.setattr(
        entry.status_module,
        "run",
        lambda **kw: seen.__setitem__("status", seen["status"] + 1) or 0,
    )
    return seen


@pytest.mark.parametrize(
    "argv", [["status", "--help"], ["status", "-h"], ["restart", "redis", "--help"]]
)
def test_help_flag_after_verb_shows_help_not_verb(spy, argv):
    rc = entry.main(argv)
    assert rc == 0
    assert spy["help"] == 1
    assert spy["status"] == 0  # the verb must NOT run


def test_bare_verb_still_runs(spy):
    rc = entry.main(["status"])
    assert rc == 0
    assert spy["help"] == 0
    assert spy["status"] == 1


def test_help_verb_alone_shows_help(spy):
    assert entry.main(["help"]) == 0
    assert spy["help"] == 1
