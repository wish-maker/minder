"""`start` verb — ported from scripts/lib/commands.sh cmd_start (#7, Stage 2).

Pure orchestration: it calls, in order, the ported pieces that now all exist —
preflight (prereqs, GPU, access/AI/compute validation), env self-heal, network
creation, service startup, the health wait, and the health report. Each step is
individually verified by its own gate script; this module is verified as a whole
under the gate's docker shim (which makes the waits/health instant + deterministic)
by scripts/gate/start_cmd_verify.sh.
"""

from . import env, health, infra, lifecycle, preflight


def run() -> int:
    preflight.check_prerequisites()
    env.prepare_env()
    preflight.validate_gpu_environment()
    # bash cmd_start runs under `set -e`: a validator returning 1 (invalid
    # ACCESS_MODE / AI_COMPUTE_MODE / COMPUTE_RESOURCE_PROFILE, or external AI mode
    # with no URL) aborts before the stack comes up. Mirror that — don't boot a
    # half-configured stack after a config error was logged.
    if (
        preflight.validate_access_mode() != 0
        or preflight.validate_ai_compute_mode() != 0
        or preflight.validate_compute_resource_profile() != 0
    ):
        return 1
    infra.create_networks()
    lifecycle.start_services()
    lifecycle.wait_for_services()
    health.run_health_checks()
    return 0
