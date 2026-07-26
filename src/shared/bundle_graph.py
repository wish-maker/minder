"""Pure bundle claim-graph brain — shared by the setup CLI and the registry API.

This is the reference-counted GC model from ``docs/architecture/bundles.md``: a service
is UP iff ≥1 **enabled** bundle **claims** it; a service claimed by 0 enabled bundles is
an **orphan**. The logic here is **pure** — it takes the bundle→claims map and the
enable-state as data and computes derived facts (enabled/active/orphan/claimants). All
I/O (reading the compose file / ``bundles.state.json``, running ``docker compose``,
logging) stays in the callers, so both the stdlib-only host CLI (``scripts/setup``) and
the FastAPI registry can import this same brain (#65).

Stdlib-only (no YAML lib, no third-party deps) so the setup CLI can import it.
"""

from __future__ import annotations

import json
import re

# ── Compose-label derivation ───────────────────────────────────────────────────
# Bundle membership is the Compose file's `minder.bundle=<comma-list>` labels (single
# source of truth). Parsed with a regex line-scan (the versions.py precedent — no YAML
# lib in the setup CLI). A comma-list lets one service be claimed by several bundles
# (ollama ∈ inference,rag,chat).
_TOPLEVEL_RE = re.compile(r"^[A-Za-z0-9_-]+:\s*(#.*)?$")  # 0-indent section key
_SERVICE_RE = re.compile(r"^  ([A-Za-z0-9._-]+):\s*(#.*)?$")  # 2-indent service key
_BUNDLE_LABEL_RE = re.compile(r"minder\.bundle=([A-Za-z0-9,_-]+)")

CORE_BUNDLE = "core"


def parse_bundle_labels(compose_text: str) -> dict[str, tuple[str, ...]]:
    """Build ``{bundle: (services...)}`` from a compose file's ``minder.bundle=`` labels.

    Walks the ``services:`` section tracking the current 2-indent service key and
    attributes each ``minder.bundle=`` label (comma-split) to it. Order within a bundle
    follows compose order (display-only; the refcount uses set membership).
    """
    claims: dict[str, list[str]] = {}
    in_services = False
    current: str | None = None
    for line in compose_text.splitlines():
        if _TOPLEVEL_RE.match(line):
            in_services = line.split(":", 1)[0] == "services"
            current = None
            continue
        if not in_services:
            continue
        svc = _SERVICE_RE.match(line)
        if svc:
            current = svc.group(1)
            continue
        label = _BUNDLE_LABEL_RE.search(line)
        if current and label:
            for bundle in label.group(1).split(","):
                svcs = claims.setdefault(bundle, [])
                if current not in svcs:
                    svcs.append(current)
    return {bundle: tuple(svcs) for bundle, svcs in claims.items()}


# ── Enable-state parsing ─────────────────────────────────────────────────────────
def parse_state(text: str) -> dict:
    """Parse ``bundles.state.json`` text → ``{bundle: {enabled: bool}}``.

    Corrupt/invalid-JSON/non-dict → ``{}`` (everything defaults to enabled). The file is
    hand-editable, so a per-bundle value that is valid JSON but the wrong shape (e.g.
    ``{"rag": false}`` instead of ``{"rag": {"enabled": false}}``) is dropped rather than
    crashing callers that index into it — it degrades to "defaults to enabled".
    """
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)}


# ── The claim graph ──────────────────────────────────────────────────────────────
class ClaimGraph:
    """Reference-counted view over a bundle→claims map and an enable-state snapshot.

    Pure and cheap to construct — callers build one from the current map + state (read
    fresh each time) and ask it derived questions.
    """

    def __init__(
        self,
        claims: dict[str, tuple[str, ...]],
        state: dict,
        core_bundle: str = CORE_BUNDLE,
    ) -> None:
        self._claims = claims
        self._state = state
        self._core = core_bundle

    def is_enabled(self, name: str) -> bool:
        """True unless the state explicitly disables the bundle. ``core`` is always on
        (the kernel); an absent key → enabled (so the default path is unchanged)."""
        if name == self._core:
            return True
        return bool(self._state.get(name, {}).get("enabled", True))

    def enabled_bundles(self, exclude: str | None = None) -> set[str]:
        return {n for n in self._claims if n != exclude and self.is_enabled(n)}

    def claimants(self, service: str, enabled: set[str] | None = None) -> set[str]:
        """Enabled bundles that claim ``service`` — everything keeping it alive; empty
        → the service is orphaned."""
        if enabled is None:
            enabled = self.enabled_bundles()
        return {b for b in enabled if service in self._claims.get(b, ())}

    def service_active(self, service: str) -> bool:
        """Should ``service`` run? Yes iff a bundle claiming it is enabled. An unclaimed
        service (not in the map) defaults to active so a gap never silently drops it."""
        claimants = [b for b in self._claims if service in self._claims[b]]
        if not claimants:
            return True
        return any(self.is_enabled(b) for b in claimants)

    def orphans_after(self, disabling: str) -> list[str]:
        """Services of ``disabling`` that no OTHER enabled bundle claims — safe to stop
        once this bundle is off. Deterministic order."""
        remaining = self.enabled_bundles(exclude=disabling)
        return sorted(
            s
            for s in self._claims.get(disabling, ())
            if not self.claimants(s, remaining)
        )

    def orphaned_services(self) -> list[str]:
        """Every service claimed by NO enabled bundle — safe to stop. What
        ``start``/``reconcile`` converge on. Deterministic order."""
        enabled = self.enabled_bundles()
        return sorted(
            {
                s
                for b in self._claims
                if not self.is_enabled(b)
                for s in self._claims[b]
                if not self.claimants(s, enabled)
            }
        )
