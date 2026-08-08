"""Regression guard: openwebui_data/qdrant_data must stay `external: true`.

Found live on the Pi: these two named volumes were created bare-named
("openwebui_data"/"qdrant_data", no project-name prefix) at some point
predating the rest of the stack -- every other real-data volume (postgres_data,
redis_data, neo4j_data, rabbitmq_data, minio_data) correctly uses Compose's
normal "<project>_<key>" naming. Compose's default project name comes from the
CALLER's CWD basename (not a fixed value), so recreating openwebui from a
differently-named working directory silently created a NEW, empty
"<other-project>_openwebui_data" volume instead of reusing the real one --
orphaning 1.1GB of real data behind a container recreate. `external: true`
pins the exact pre-existing name so this can't drift again regardless of
invocation context. If someone "cleans up" by removing external: true here
(it looks inconsistent next to the `driver: local` volumes), the exact same
data-loss bug reappears on the next recreate from an unusual CWD.
"""

from pathlib import Path

import yaml

COMPOSE = Path(__file__).resolve().parents[2] / "docker" / "docker-compose.yml"


def _volumes():
    with open(COMPOSE) as f:
        return yaml.safe_load(f)["volumes"]


def test_openwebui_data_is_external():
    assert _volumes()["openwebui_data"] == {"external": True}


def test_qdrant_data_is_external():
    assert _volumes()["qdrant_data"] == {"external": True}


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
