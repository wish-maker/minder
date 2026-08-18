"""Unit tests for the `uninstall` verb (scripts/setup/uninstall.py) --
previously only verified non-destructively under DRY_RUN by
scripts/gate/uninstall_verify.sh; the module itself had zero Python unit
tests (17%). docker/infra/bundles/log are all monkeypatched -- no real
Docker calls, no real stdin read outside the interactive-confirm tests.
"""

from scripts.setup import uninstall


def _patch_collaborators(monkeypatch, calls, *, reset_state_result=True):
    monkeypatch.setattr(
        uninstall.docker,
        "compose_all",
        lambda *args: calls.append(("compose_all", args)),
    )
    monkeypatch.setattr(
        uninstall.infra, "remove_networks", lambda: calls.append(("remove_networks",))
    )
    monkeypatch.setattr(
        uninstall.bundles,
        "reset_state",
        lambda: calls.append(("reset_state",)) or reset_state_result,
    )


def test_plain_uninstall_stops_services_without_purging(monkeypatch, capfd):
    calls = []
    _patch_collaborators(monkeypatch, calls)

    rc = uninstall.run()

    out = capfd.readouterr().out
    assert rc == 0
    assert calls == [("compose_all", ("down",))]
    assert "data preserved" in out
    assert "uninstall --purge" in out


def test_purge_noninteractive_skips_confirmation_and_wipes_everything(
    monkeypatch, capfd
):
    monkeypatch.setattr(uninstall.config, "INTERACTIVE", False)
    calls = []
    _patch_collaborators(monkeypatch, calls)

    rc = uninstall.run("--purge")

    out = capfd.readouterr().out
    assert rc == 0
    assert calls == [
        ("compose_all", ("down", "-v", "--remove-orphans")),
        ("remove_networks",),
        ("reset_state",),
    ]
    assert "NONINTERACTIVE" in out
    assert "Bundle selection reset" in out
    assert "Full uninstall complete" in out


def test_purge_interactive_confirmed_with_delete_proceeds(monkeypatch):
    monkeypatch.setattr(uninstall.config, "INTERACTIVE", True)
    monkeypatch.setattr(uninstall.sys.stdin, "readline", lambda: "DELETE\n")
    calls = []
    _patch_collaborators(monkeypatch, calls)

    rc = uninstall.run("--purge")

    assert rc == 0
    assert ("compose_all", ("down", "-v", "--remove-orphans")) in calls


def test_purge_interactive_cancelled_without_exact_delete(monkeypatch, capfd):
    monkeypatch.setattr(uninstall.config, "INTERACTIVE", True)
    monkeypatch.setattr(uninstall.sys.stdin, "readline", lambda: "no\n")
    calls = []
    _patch_collaborators(monkeypatch, calls)

    rc = uninstall.run("--purge")

    out = capfd.readouterr().out
    assert rc == 0
    assert calls == []
    assert "Uninstall cancelled." in out


def test_purge_skips_bundle_reset_success_message_when_nothing_reset(
    monkeypatch, capfd
):
    monkeypatch.setattr(uninstall.config, "INTERACTIVE", False)
    calls = []
    _patch_collaborators(monkeypatch, calls, reset_state_result=False)

    uninstall.run("--purge")

    out = capfd.readouterr().out
    assert "Bundle selection reset" not in out
    assert "Full uninstall complete" in out


def test_purge_emits_the_destructive_banner(monkeypatch, capfd):
    monkeypatch.setattr(uninstall.config, "INTERACTIVE", False)
    calls = []
    _patch_collaborators(monkeypatch, calls)

    uninstall.run("--purge")

    out = capfd.readouterr().out
    assert "DESTRUCTIVE OPERATION" in out
    assert "CANNOT BE UNDONE" in out
    assert "All services AND data volumes will be deleted." in out
