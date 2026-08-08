"""Regression guard: openwebui_data/qdrant_data must stay `external: true`
with an OVERRIDABLE name, not a hardcoded literal.

Found live on the Pi: these two named volumes were created bare-named
("openwebui_data"/"qdrant_data", no project-name prefix) at some point in
that host's own history -- every other real-data volume there (postgres_data,
redis_data, neo4j_data, rabbitmq_data, minio_data) correctly uses Compose's
normal "<project>_<key>" naming. A container recreate silently created a NEW,
empty "minder_openwebui_data" instead of reusing the real one, orphaning
1.1GB of real data. `external: true` with a HARDCODED bare name fixed the Pi
-- but a second real deployment (hantal) has no bare-named volume at all,
only the correctly-prefixed "minder_openwebui_data"; a hardcoded bare name
would have made Compose fail there with "external volume not found" on its
next restart (confirmed live via `docker compose config` before this was
caught). The bare name is one host's own historical drift, not a fact about
this compose file's normal behavior -- so the name is an overridable
`${OPENWEBUI_DATA_VOLUME_NAME:-minder_openwebui_data}`, defaulting to the
standard name every fresh install (and hantal) actually has; only the Pi's
own .env overrides it to the legacy bare name. If someone "cleans up" by
hardcoding a literal name here again, the exact same "works on one host,
breaks the next restart on another" bug reappears.
"""

from pathlib import Path

import yaml

COMPOSE = Path(__file__).resolve().parents[2] / "docker" / "docker-compose.yml"


def _volumes():
    with open(COMPOSE) as f:
        return yaml.safe_load(f)["volumes"]


def test_openwebui_data_is_external_with_overridable_name():
    assert _volumes()["openwebui_data"] == {
        "external": True,
        "name": "${OPENWEBUI_DATA_VOLUME_NAME:-minder_openwebui_data}",
    }


def test_qdrant_data_is_external_with_overridable_name():
    assert _volumes()["qdrant_data"] == {
        "external": True,
        "name": "${QDRANT_DATA_VOLUME_NAME:-minder_qdrant_data}",
    }


def test_other_real_data_volumes_are_not_external():
    """Sanity check the fix is scoped to the two drifted volumes, not a
    blanket change -- these must stay Compose-managed (`driver: local`)."""
    volumes = _volumes()
    for name in (
        "postgres_data",
        "redis_data",
        "neo4j_data",
        "rabbitmq_data",
        "minio_data",
    ):
        assert volumes[name] == {"driver": "local"}, name
