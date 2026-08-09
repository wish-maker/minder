"""Guard the Compose-label-derived bundle claim map (#65).

The bundle → services map is derived from `minder.bundle=` Compose labels (the compose
file is the single source of truth). This test pins the derived map to the reviewed
spec, so a mislabelled service, a new unlabelled service, or a typo'd bundle name is
caught in CI rather than silently changing the refcount graph.
"""

from scripts.setup import bundles

# The reviewed bundle map (docs/architecture/bundles.md). Compared as sets — order
# within a bundle is display-only (the refcount uses membership).
EXPECTED = {
    "core": {
        "traefik",
        "authelia",
        "docker-socket-proxy",
        "postgres",
        "redis",
        "rabbitmq",
        "neo4j",
        "minio",
        "schema-registry",
        "api-gateway",
        "plugin-registry",
        "plugin-state-manager",
        "marketplace",
        "client",
    },
    "monitoring": {
        "influxdb",
        "telegraf",
        "prometheus",
        "grafana",
        "alertmanager",
        "jaeger",
        "otel-collector",
        "postgres-exporter",
        "redis-exporter",
        "rabbitmq-exporter",
        "node-exporter",
        "cadvisor",
        "blackbox-exporter",
    },
    "inference": {"ollama", "model-management"},
    "rag": {"rag-pipeline", "qdrant", "ollama"},
    "graph-rag": {"graph-rag"},
    "chat": {"openwebui", "rag-pipeline", "ollama"},
    "voice": {"tts-stt"},
}


def test_derived_map_matches_reviewed_spec():
    derived = {name: set(b["claims"]) for name, b in bundles.BUNDLES.items()}
    assert derived == EXPECTED


def test_multi_claim_services_shared_across_bundles():
    # These shared claims are what stop the refcount from orphaning a service another
    # enabled bundle still needs (bundles.md).
    assert "ollama" in bundles.BUNDLES["inference"]["claims"]
    assert "ollama" in bundles.BUNDLES["rag"]["claims"]
    assert "ollama" in bundles.BUNDLES["chat"]["claims"]
    assert "rag-pipeline" in bundles.BUNDLES["rag"]["claims"]
    assert "rag-pipeline" in bundles.BUNDLES["chat"]["claims"]


def test_bundle_names_match_profile_policy():
    # The derived bundle names must equal core + the optional-bundle policy list, so a
    # stray label can't introduce a bundle no profile knows about (and vice versa).
    assert set(bundles.BUNDLES) == {bundles.CORE_BUNDLE, *bundles._OPTIONAL_BUNDLES}


def test_no_duplicate_claims():
    for name, b in bundles.BUNDLES.items():
        claims = b["claims"]
        assert len(claims) == len(set(claims)), f"duplicate claims in bundle {name!r}"
