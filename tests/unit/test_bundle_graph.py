"""Unit tests for the shared pure bundle brain (`shared.bundle_graph`, #65).

This is the logic both the setup CLI and the future registry API import, so it is
tested directly (independent of either front-end): label parsing, corrupt-tolerant
state parsing, and the reference-counted claim graph.
"""

from shared.bundle_graph import ClaimGraph, parse_bundle_labels, parse_state

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
