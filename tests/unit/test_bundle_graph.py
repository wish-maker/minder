"""Unit tests for the shared pure bundle brain (`shared.bundle_graph`, #65).

This is the logic both the setup CLI and the future registry API import, so it is
tested directly (independent of either front-end): label parsing, corrupt-tolerant
state parsing, and the reference-counted claim graph.
"""

from shared.bundle_graph import (
    ClaimGraph,
    bindings_from_plugin_manifests,
    claims_from_plugin_manifests,
    parse_bundle_labels,
    parse_plugin_manifest,
    parse_state,
)

_COMPOSE = """\
services:
  ollama:
    labels:
    - minder.bundle=inference,rag,chat
    image: ollama/ollama
  qdrant:
    labels:
    - minder.bundle=rag
  grafana:
    labels:
    - traefik.enable=true
    - minder.bundle=monitoring
  core-svc:
    labels: [minder.bundle=core]
volumes:
  ollama_data:
    labels:
    - minder.bundle=should-be-ignored-outside-services
"""


def test_parse_bundle_labels_multi_and_sections():
    m = parse_bundle_labels(_COMPOSE)
    assert m["inference"] == ("ollama",)
    assert set(m["rag"]) == {"ollama", "qdrant"}
    assert m["chat"] == ("ollama",)
    assert m["monitoring"] == ("grafana",)  # label coexists with traefik label
    assert m["core"] == ("core-svc",)
    # a minder.bundle in the volumes: section must NOT leak into the map
    assert "should-be-ignored-outside-services" not in m


def test_parse_state_tolerates_corruption():
    assert parse_state('{"rag": {"enabled": false}}') == {"rag": {"enabled": False}}
    assert parse_state("not json") == {}
    assert parse_state("[1,2,3]") == {}  # top-level not a dict
    # valid JSON, wrong per-entry shape → that entry dropped (degrade to enabled)
    assert parse_state('{"rag": false, "chat": {"enabled": true}}') == {
        "chat": {"enabled": True}
    }


_CLAIMS = {
    "core": ("traefik", "postgres"),
    "inference": ("ollama", "model-management"),
    "rag": ("rag-pipeline", "qdrant", "ollama"),
    "chat": ("openwebui", "rag-pipeline", "ollama"),
    "voice": ("tts-stt",),
}


def _graph(state):
    return ClaimGraph(_CLAIMS, state)


def test_core_always_enabled():
    g = _graph({"core": {"enabled": False}})  # even if someone writes this
    assert g.is_enabled("core") is True


def test_absent_key_defaults_enabled():
    assert _graph({}).is_enabled("voice") is True


def test_service_active_via_refcount():
    # voice off → tts-stt inactive; ollama stays active (claimed by inference/rag/chat)
    g = _graph({"voice": {"enabled": False}})
    assert g.service_active("tts-stt") is False
    assert g.service_active("ollama") is True


def test_unclaimed_service_defaults_active():
    assert _graph({}).service_active("mystery-service") is True


def test_orphans_after_shared_claim_kept():
    # disabling rag: qdrant orphaned, but ollama/rag-pipeline kept by chat
    g = _graph({})
    assert g.orphans_after("rag") == ["qdrant"]


def test_orphaned_services_only_when_all_claimants_off():
    # inference off but rag/chat still claim ollama → ollama NOT orphaned; only
    # model-management (claimed solely by inference) is.
    g = _graph({"inference": {"enabled": False}})
    assert g.orphaned_services() == ["model-management"]


# ── Plugin manifest parsing (#65 item 5) ────────────────────────────────────────
_MANIFEST_FULL = """\
bundle: chat
manager: true
claims:
  - service: my-vector-db
    self_hostable: true
    address_env: MY_VECTOR_DB_URL
    spec_ref: service.yml
  - service: another-service
    self_hostable: false
"""


def test_parse_plugin_manifest_full_shape():
    parsed = parse_plugin_manifest(_MANIFEST_FULL)
    assert parsed["bundle"] == "chat"
    assert parsed["manager"] is True
    assert parsed["claims"] == [
        {
            "service": "my-vector-db",
            "self_hostable": True,
            "address_env": "MY_VECTOR_DB_URL",
            "spec_ref": "service.yml",
        },
        {
            "service": "another-service",
            "self_hostable": False,
            "address_env": None,
            "spec_ref": None,
        },
    ]


def test_parse_plugin_manifest_minimal_no_claims():
    parsed = parse_plugin_manifest("bundle: monitoring\n")
    assert parsed == {"bundle": "monitoring", "manager": False, "claims": []}


def test_parse_plugin_manifest_no_bundle_key_is_fail_soft():
    # A malformed/in-progress manifest must not raise -- just contributes nothing.
    parsed = parse_plugin_manifest("claims:\n  - service: orphan-claim\n")
    assert parsed["bundle"] is None


def test_parse_plugin_manifest_empty_text():
    assert parse_plugin_manifest("") == {"bundle": None, "manager": False, "claims": []}


def test_claims_from_plugin_manifests_merges_multiple():
    other = "bundle: chat\nclaims:\n  - service: yet-another\n"
    merged = claims_from_plugin_manifests([_MANIFEST_FULL, other])
    assert set(merged["chat"]) == {"my-vector-db", "another-service", "yet-another"}


def test_claims_from_plugin_manifests_skips_bundleless():
    merged = claims_from_plugin_manifests(
        ["claims:\n  - service: orphan-claim\n", _MANIFEST_FULL]
    )
    assert "orphan-claim" not in [s for svcs in merged.values() for s in svcs]


def test_claims_from_plugin_manifests_no_duplicate_services():
    dup = "bundle: chat\nclaims:\n  - service: my-vector-db\n"
    merged = claims_from_plugin_manifests([_MANIFEST_FULL, dup])
    assert merged["chat"].count("my-vector-db") == 1


def test_claims_from_plugin_manifests_empty_input():
    assert claims_from_plugin_manifests([]) == {}


def test_bindings_from_plugin_manifests_extracts_address_env():
    bindings = bindings_from_plugin_manifests([_MANIFEST_FULL])
    assert bindings == {"my-vector-db": "MY_VECTOR_DB_URL"}


def test_bindings_from_plugin_manifests_skips_claims_without_address_env():
    # "another-service" has self_hostable=false and no address_env -- a pure
    # "I need this platform service" claim, not something bindable.
    bindings = bindings_from_plugin_manifests([_MANIFEST_FULL])
    assert "another-service" not in bindings


def test_claims_from_plugin_manifests_merges_into_compose_claims():
    """End-to-end: a plugin's claim + compose labels union into one claim graph,
    exactly how _load_claims()/_load() are meant to merge the two sources."""
    compose_claims = dict(parse_bundle_labels(_COMPOSE))
    plugin_claims = claims_from_plugin_manifests([_MANIFEST_FULL])
    for bundle, svcs in plugin_claims.items():
        merged = list(compose_claims.get(bundle, ()))
        for svc in svcs:
            if svc not in merged:
                merged.append(svc)
        compose_claims[bundle] = tuple(merged)
    # "chat" already claimed "ollama" via compose; now also claims the plugin's
    # two services, without losing the original claim.
    assert set(compose_claims["chat"]) == {"ollama", "my-vector-db", "another-service"}
