"""Security regression guard for #190: every non-Traefik host port in the compose
file must be bound to 127.0.0.1 (loopback), so nothing bypasses the Traefik/Authelia
front door. Only Traefik (80/443/8081) may publish on all interfaces.

Parses the compose text with the same stdlib regex-line approach as
shared/bundle_graph (no YAML dep), matching the runtime constraint.
"""

import re
from pathlib import Path

COMPOSE = (
    Path(__file__).resolve().parents[2] / "docker" / "docker-compose.yml"
)

# Only these services may bind host ports on all interfaces (the public front door
# + the IP-whitelisted dashboard). Everything else must be 127.0.0.1-only.
PUBLIC_SERVICES = {"traefik"}

_SVC = re.compile(r"^  ([a-z][a-z0-9_-]*):\s*$")
_PORTS = re.compile(r"^    ports:\s*$")
_PORT_LINE = re.compile(r'^\s*-\s*"?(?P<hostspec>[^":]*:)?\d+:\d+')


def _host_port_map():
    """service -> list of raw port-mapping lines (host-published ports only)."""
    text = COMPOSE.read_text(encoding="utf-8")
    svc, in_ports, out = None, False, {}
    for ln in text.splitlines():
        m = _SVC.match(ln)
        if m:
            svc, in_ports = m.group(1), False
            continue
        if _PORTS.match(ln):
            in_ports = True
            continue
        if in_ports:
            if re.match(r"^    - ", ln):
                out.setdefault(svc, []).append(ln.strip())
            elif not re.match(r"^\s*#", ln) and ln.strip():
                in_ports = False
    return out


def test_non_traefik_host_ports_are_loopback_bound():
    """#190: no non-Traefik service may publish a port on 0.0.0.0."""
    offenders = []
    for svc, lines in _host_port_map().items():
        if svc in PUBLIC_SERVICES:
            continue
        for ln in lines:
            # a host-published mapping like `- "8000:8000"` (no 127.0.0.1: prefix)
            if _PORT_LINE.match(ln) and "127.0.0.1:" not in ln:
                offenders.append(f"{svc}: {ln}")
    assert not offenders, (
        "Non-Traefik host ports must be bound to 127.0.0.1 (#190) — these publish "
        "on all interfaces and bypass Traefik/Authelia:\n  " + "\n  ".join(offenders)
    )


def test_traefik_still_public():
    """The front door must stay reachable — traefik's 80/443 are NOT loopback."""
    traefik = _host_port_map().get("traefik", [])
    joined = " ".join(traefik)
    assert "80:80" in joined and "443:443" in joined
    assert "127.0.0.1:" not in joined  # traefik ports stay public
