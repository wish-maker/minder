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
_IMAGE_RE = re.compile(r"^    image:\s*(\S+)\s*(#.*)?$")  # 4-indent image: key

CORE_BUNDLE = "core"


# ── Plugin manifest derivation (#65 item 5) ────────────────────────────────────
# The claim graph's second source (docs/architecture/bundles.md's "three sources"):
# a plugin declares its own claims in `src/plugins/<name>/manifest.yml` — the ADR's
# own described shape (`bundle`, `claims[]` with `self_hostable`/`address_env`/
# `spec_ref`, `manager?`). No plugin ships one of these yet (deliberately not
# retrofitted onto the 6 existing first-party module plugins, which own no service
# of their own and are correctly gated by their own enable/disable flag instead,
# not a bundle claim — see the ADR's `plugin` vocabulary entry) — this is
# foundational infrastructure for a FUTURE self-hosting plugin, so with zero
# manifests present today every function below returns empty, changing nothing.
#
# Same regex-line-scan convention as parse_bundle_labels (no YAML lib): a claim is
# a 2-indent `- service: <name>` list item under a top-level `claims:` key, with
# its own 4-indent sub-fields.
_MANIFEST_BUNDLE_RE = re.compile(r"^bundle:\s*([A-Za-z0-9_-]+)\s*(#.*)?$")
_MANIFEST_MANAGER_RE = re.compile(r"^manager:\s*(true|false)\s*(#.*)?$", re.IGNORECASE)
_MANIFEST_CLAIMS_KEY_RE = re.compile(r"^claims:\s*(#.*)?$")
_CLAIM_ITEM_RE = re.compile(r"^  -\s*service:\s*([A-Za-z0-9._-]+)\s*(#.*)?$")
_CLAIM_FIELD_RE = re.compile(r"^    ([a-z_]+):\s*(\S+)\s*(#.*)?$")


def parse_plugin_manifest(manifest_text: str) -> dict:
    """Parse one ``manifest.yml``'s text → ``{"bundle": str|None, "manager": bool,
    "claims": [{"service": str, "self_hostable": bool, "address_env": str|None,
    "spec_ref": str|None}, ...]}``.

    Fail-soft like ``parse_state``: a manifest with no ``bundle:`` key contributes
    nothing (``bundle`` is ``None``) rather than raising — a malformed or
    in-progress manifest shouldn't be able to crash the whole claim graph.
    """
    bundle: str | None = None
    manager = False
    claims: list[dict] = []
    current: dict | None = None
    for line in manifest_text.splitlines():
        m = _MANIFEST_BUNDLE_RE.match(line)
        if m:
            bundle = m.group(1)
            continue
        m = _MANIFEST_MANAGER_RE.match(line)
        if m:
            manager = m.group(1).lower() == "true"
            continue
        if _MANIFEST_CLAIMS_KEY_RE.match(line):
            continue
        m = _CLAIM_ITEM_RE.match(line)
        if m:
            current = {
                "service": m.group(1),
                "self_hostable": False,
                "address_env": None,
                "spec_ref": None,
            }
            claims.append(current)
            continue
        m = _CLAIM_FIELD_RE.match(line)
        if m and current is not None and m.group(1) in current:
            key, value = m.group(1), m.group(2)
            current[key] = (
                (value.lower() == "true") if key == "self_hostable" else value
            )
    return {"bundle": bundle, "manager": manager, "claims": claims}


def claims_from_plugin_manifests(
    manifest_texts: "list[str]",
) -> dict[str, tuple[str, ...]]:
    """Merge many manifests' claims → the same ``{bundle: (services...)}`` shape
    ``parse_bundle_labels`` produces, so a caller can union the two claim sources
    before constructing a ``ClaimGraph``. A manifest with no ``bundle:`` (or no
    ``claims:``) contributes nothing."""
    claims: dict[str, list[str]] = {}
    for text in manifest_texts:
        parsed = parse_plugin_manifest(text)
        bundle = parsed["bundle"]
        if not bundle:
            continue
        for claim in parsed["claims"]:
            svcs = claims.setdefault(bundle, [])
            if claim["service"] not in svcs:
                svcs.append(claim["service"])
    return {bundle: tuple(svcs) for bundle, svcs in claims.items()}


def bindings_from_plugin_manifests(manifest_texts: "list[str]") -> dict[str, str]:
    """Merge many manifests' ``address_env`` fields → ``{service: env_var_name}``,
    the same shape as ``bundles.EXTERNAL_BINDINGS`` — so a plugin-declared claim
    can resolve to an external binding exactly like ollama/tts-stt do today, without
    the caller hardcoding every service name. Claims with no ``address_env`` (pure
    "I need this platform service" claims, not self-hostable/bindable ones) are
    skipped."""
    bindings: dict[str, str] = {}
    for text in manifest_texts:
        for claim in parse_plugin_manifest(text)["claims"]:
            if claim["address_env"]:
                bindings[claim["service"]] = claim["address_env"]
    return bindings


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


def parse_service_images(compose_text: str) -> dict[str, str]:
    """Build ``{service: image}`` (the full ``repo/name:tag``, untouched) from a
    compose file's per-service ``image:`` key -- lets bundle UIs show operators
    which Docker image version each claimed service actually runs, without any
    new docker-socket-proxy capability (the versions are static, pinned in this
    same file already being read for ``minder.bundle=`` labels).

    Same line-scan convention and section-tracking as ``parse_bundle_labels``. A
    service with no ``image:`` key (e.g. one built from a local ``build:`` block
    instead of a pulled image) is simply absent from the result -- callers should
    treat a missing entry as "custom build", not an error.
    """
    images: dict[str, str] = {}
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
        m = _IMAGE_RE.match(line)
        if current and m:
            images[current] = m.group(1)
    return images


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
