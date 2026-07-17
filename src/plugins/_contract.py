"""Shared contract for first-party module plugins.

Single source of truth so plugins don't each redefine ``PluginMetadata`` or
re-guess the lifecycle. Import from here instead of copying the dataclass:

    from plugins._contract import PluginMetadata

Plugins are **duck-typed** — the registry loader matches a class by the presence
of ``register`` (see plugin_loader.py), so a plugin need not inherit anything.
``Plugin`` below is a ``Protocol`` you can type-check against (editor / mypy); it
documents the exact lifecycle the registry drives and the one easy-to-miss rule:
``health_check()`` MUST return ``{"healthy": <bool>, ...}`` (monitoring reads
``health.get("healthy")``).

This is a module (``plugins._contract``), not a plugin dir, so the loader — which
only iterates sub-directories — never tries to load it.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Protocol, runtime_checkable

__all__ = ["PluginMetadata", "Plugin"]


@dataclass
class PluginMetadata:
    """Return shape for ``register()`` — the fields the registry loader reads
    (``src/services/plugin-registry/core/plugin_loader.py``): name/version/
    description/author/dependencies/capabilities/data_sources/databases/
    registered_at (a ``datetime`` — the loader calls ``.isoformat()`` on it)."""

    name: str
    version: str
    description: str
    author: str
    dependencies: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    data_sources: List[str] = field(default_factory=list)
    databases: List[str] = field(default_factory=list)
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@runtime_checkable
class Plugin(Protocol):
    """The async lifecycle the registry drives. Match these methods (duck-typed);
    inheriting is optional — use it for editor/mypy checking."""

    async def register(self) -> PluginMetadata:
        ...

    async def initialize(self) -> None:
        ...

    async def health_check(self) -> Dict:  # MUST return {"healthy": <bool>, ...}
        ...

    async def collect_data(self) -> Dict:
        ...

    async def analyze(self) -> Dict:
        ...

    async def shutdown(self) -> None:
        ...


# Optional: a plugin MAY expose write/execute actions over HTTP by declaring a
# class attribute ``ACTIONS`` — a frozenset of method names invokable via
# ``POST /v1/plugins/<name>/actions/<method>`` (JWT-gated; the JSON body is passed
# as kwargs). Only names in ACTIONS are reachable — nothing else on the instance.
# Reads use /collect (collect_data) + /analysis (analyze); ACTIONS is for state
# changes (e.g. the telegraf plugin's set_managed_region / reload).
