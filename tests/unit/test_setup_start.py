"""Unit tests for `start.run()` (scripts/setup/start.py) -- pure orchestration
over preflight/env/infra/lifecycle/health, previously untested at the Python
unit level (only exercised end-to-end by scripts/gate/start_cmd_verify.sh's
docker shim). Every collaborator is monkeypatched; these tests assert call
order and the two `set -e`-mirroring short-circuit branches.
"""

from scripts.setup import start


def _patch_all(monkeypatch, calls, *, ai_mode_rc=0, resource_profile_rc=0):
    monkeypatch.setattr(
        start.preflight,
        "check_prerequisites",
        lambda: calls.append("check_prerequisites"),
    )
    monkeypatch.setattr(start.env, "prepare_env", lambda: calls.append("prepare_env"))
    monkeypatch.setattr(
        start.preflight,
        "validate_gpu_environment",
        lambda: calls.append("validate_gpu_environment"),
    )

    def _ai_mode():
        calls.append("validate_ai_compute_mode")
        return ai_mode_rc

    def _resource_profile():
        calls.append("validate_compute_resource_profile")
        return resource_profile_rc

    monkeypatch.setattr(start.preflight, "validate_ai_compute_mode", _ai_mode)
    monkeypatch.setattr(
        start.preflight, "validate_compute_resource_profile", _resource_profile
    )
    monkeypatch.setattr(
        start.infra, "create_networks", lambda: calls.append("create_networks")
    )
    monkeypatch.setattr(
        start.infra,
        "migrate_volume_names",
        lambda: calls.append("migrate_volume_names"),
    )
    monkeypatch.setattr(
        start.lifecycle, "start_services", lambda: calls.append("start_services")
    )
    monkeypatch.setattr(
        start.lifecycle,
        "wait_for_services",
        lambda: calls.append("wait_for_services"),
    )
    monkeypatch.setattr(
        start.health,
        "run_health_checks",
        lambda: calls.append("run_health_checks"),
    )


def test_happy_path_runs_every_step_in_order_and_returns_zero(monkeypatch):
    calls = []
    _patch_all(monkeypatch, calls)

    rc = start.run()

    assert rc == 0
    assert calls == [
        "check_prerequisites",
        "prepare_env",
        "validate_gpu_environment",
        "validate_ai_compute_mode",
        "validate_compute_resource_profile",
        "create_networks",
        "migrate_volume_names",
        "start_services",
        "wait_for_services",
        "run_health_checks",
    ]


def test_invalid_ai_compute_mode_aborts_before_infra_comes_up(monkeypatch):
    calls = []
    _patch_all(monkeypatch, calls, ai_mode_rc=1)

    rc = start.run()

    assert rc == 1
    assert calls == [
        "check_prerequisites",
        "prepare_env",
        "validate_gpu_environment",
        "validate_ai_compute_mode",
    ]
    assert "create_networks" not in calls
    assert "start_services" not in calls


def test_invalid_resource_profile_aborts_before_infra_comes_up(monkeypatch):
    calls = []
    _patch_all(monkeypatch, calls, resource_profile_rc=1)

    rc = start.run()

    assert rc == 1
    assert calls == [
        "check_prerequisites",
        "prepare_env",
        "validate_gpu_environment",
        "validate_ai_compute_mode",
        "validate_compute_resource_profile",
    ]
    assert "create_networks" not in calls


def test_ai_compute_mode_short_circuits_before_resource_profile_check(monkeypatch):
    calls = []
    _patch_all(monkeypatch, calls, ai_mode_rc=1, resource_profile_rc=1)

    rc = start.run()

    assert rc == 1
    assert "validate_compute_resource_profile" not in calls
