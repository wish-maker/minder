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
    preflight.validate_access_mode()
    preflight.validate_ai_compute_mode()
    preflight.validate_compute_resource_profile()
    infra.create_networks()
    lifecycle.start_services()
    lifecycle.wait_for_services()
    health.run_health_checks()
    return 0
