"""
Core Database Module

Owns the PostgreSQL connection pool and all plugin persistence: table creation,
loading the plugin cache from the database, and upserting plugin rows. The pool is
created lazily and lives here (it is the only reassigned piece of shared state);
the in-memory caches live in ``core.state``.
"""

import asyncio
import json
import pathlib
import sys

from core.state import logger, plugins_db
from models import PluginInfo

from config import settings

# Shared pool factory owns create_pool construction (#49). main.py inserts /app/src
# before importing this module; guard anyway so import order can't break it.
if "/app/src" not in sys.path:
    sys.path.insert(0, "/app/src")

from shared.db.pool import create_pg_pool  # noqa: E402
from shared.db.schema import apply_schema  # noqa: E402

# Declarative schema lives at the service root (schema.sql — #17).
_SCHEMA_PATH = pathlib.Path(__file__).parent.parent / "schema.sql"

# Global connection pool (lazily created by get_postgres_connection)
postgres_pool = None
# Guards lazy pool creation so two concurrent first-callers don't each build a
# pool (the second assignment would win, leaking the first pool's connections).
_pool_lock = asyncio.Lock()


def _json_list(val) -> list:
    """Decode a list column that comes back as a JSON string (JSONB/TEXT via
    asyncpg), an already-decoded list, or NULL. Returns [] on anything unusable so
    a persisted plugin never fails to reload over a bad/empty value (#59)."""
    if not val:
        return []
    if isinstance(val, list):
        return val
    try:
        parsed = json.loads(val)
    except (ValueError, TypeError):
        return []
    return parsed if isinstance(parsed, list) else []


async def get_postgres_connection():
    """Get PostgreSQL connection pool (creating it on first use)."""
    global postgres_pool
    if postgres_pool is not None:
        return postgres_pool

    async with _pool_lock:
        if postgres_pool is not None:
            return postgres_pool

        # command_timeout=None preserves the previous behaviour (no per-command
        # timeout). hasattr fallbacks preserved for the same defaults as before.
        postgres_pool = await create_pg_pool(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            database=settings.DB_NAME,
            min_size=2,
            max_size=10,
            command_timeout=None,
        )
    return postgres_pool


async def create_plugins_table_if_not_exists():
    """Create the plugins table if absent (schema in schema.sql — #17)."""
    try:
        pool = await get_postgres_connection()
        await apply_schema(pool, _SCHEMA_PATH)
        logger.info("✅ Plugins table verified/created in PostgreSQL")

    except Exception as e:
        logger.error(f"❌ Failed to create plugins table: {e}")
        raise


async def load_plugins_from_database():
    """Load plugins from PostgreSQL database into memory cache"""
    try:
        conn = await get_postgres_connection()

        query = """
            SELECT name, version, description, author, status, enabled,
                   dependencies, capabilities, data_sources, databases,
                   health_status, last_health_check, registered_at
            FROM plugins
            ORDER BY name
        """

        rows = await conn.fetch(query)

        for row in rows:
            plugin_info = PluginInfo(
                name=row["name"],
                version=row["version"],
                description=row["description"],
                author=row["author"],
                status=row["status"],
                enabled=row["enabled"],
                dependencies=_json_list(row["dependencies"]),
                capabilities=_json_list(row["capabilities"]),
                data_sources=_json_list(row["data_sources"]),
                databases=_json_list(row["databases"]),
                registered_at=(
                    row["registered_at"].isoformat() if row["registered_at"] else None
                ),
                health_status=row["health_status"] or "unknown",
                last_health_check=(
                    row["last_health_check"].isoformat()
                    if row["last_health_check"]
                    else None
                ),
            )
            plugins_db[row["name"]] = plugin_info

        logger.info(f"✅ Loaded {len(plugins_db)} plugins from database")

    except Exception as e:
        logger.error(f"❌ Failed to load plugins from database: {e}")
        # Don't raise - allow startup to continue with empty plugins_db


async def update_plugin_in_database(plugin_name: str, **updates):
    """Update plugin in database (INSERT if not exists, UPDATE if exists)"""
    pool = await get_postgres_connection()

    try:
        # Only allow updating columns that exist in the plugins table
        allowed_columns = {
            "status",
            "enabled",
            "health_status",
            "last_health_check",
            "version",
            "description",
            "author",
            "dependencies",
            "capabilities",
            "data_sources",
            "databases",
            "stable_id",
            "marketplace_plugin_id",
        }
        valid_updates = {k: v for k, v in updates.items() if k in allowed_columns}

        if not valid_updates:
            return

        # Build parameter lists in correct order
        insert_columns = ["name"] + list(valid_updates.keys())
        insert_values = [f"${i+1}" for i in range(len(insert_columns))]

        # Build UPDATE clause for ON CONFLICT
        update_clauses = [f"{col} = EXCLUDED.{col}" for col in valid_updates.keys()]

        # Build values list (plugin_name first, then updates)
        values = [plugin_name] + list(valid_updates.values())

        # nosec B608 - SQL injection protected by allowed_columns whitelist
        # Use INSERT ... ON CONFLICT for UPSERT
        query = f"""
            INSERT INTO plugins ({', '.join(insert_columns)})
            VALUES ({', '.join(insert_values)})
            ON CONFLICT (name) DO UPDATE
              SET {', '.join(update_clauses)}
        """

        async with pool.acquire() as conn:
            await conn.execute(query, *values)
        logger.debug(
            f"Upserted plugin {plugin_name} in database: {list(valid_updates.keys())}"
        )

    except Exception as e:
        logger.error(f"Failed to update plugin {plugin_name} in database: {e}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        # #351: this used to swallow the exception entirely -- every caller in
        # routes/plugins.py (install/enable/disable) awaits this and returns a
        # 200 success response regardless of whether the DB write actually
        # happened. Re-raise so callers can convert it into an honest error.
        raise


async def find_plugin_name_by_stable_id(stable_id: str):
    """The CURRENT `name` of the plugin row carrying this stable_id, or None
    if no row has it yet (#747). Used to detect a directory rename: a plugin
    whose committed `.plugin_id` marker matches a row persisted under a
    DIFFERENT name than the one it's loading under right now."""
    if not stable_id:
        return None
    pool = await get_postgres_connection()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT name FROM plugins WHERE stable_id = $1", stable_id
        )
    return row["name"] if row else None


async def rename_plugin_row(old_name: str, new_name: str) -> None:
    """Rename an existing plugin row in place (#747) -- carries forward
    marketplace_plugin_id/config/everything else already persisted under
    `old_name`, instead of leaving it behind as an orphan while a fresh row
    gets created under `new_name` on the next upsert.

    A no-op (not an error) if `old_name == new_name` -- callers only invoke
    this after already confirming the two differ, but staying safe here
    costs nothing.
    """
    if old_name == new_name:
        return
    pool = await get_postgres_connection()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE plugins SET name = $1 WHERE name = $2", new_name, old_name
        )
    logger.info(f"Renamed plugin row (stable_id match): {old_name} -> {new_name}")


async def get_marketplace_plugin_id(plugin_name: str):
    """The marketplace catalog id this plugin was last resolved to, or None
    if it has never successfully synced (#747)."""
    pool = await get_postgres_connection()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT marketplace_plugin_id FROM plugins WHERE name = $1", plugin_name
        )
    return row["marketplace_plugin_id"] if row else None


async def load_plugin_config(plugin_name: str) -> dict:
    """Load a plugin's persisted (API-set) config overrides. {} if none/on error."""
    pool = await get_postgres_connection()
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT config FROM plugin_configs WHERE plugin_name = $1", plugin_name
            )
        if not row or row["config"] is None:
            return {}
        cfg = row["config"]
        return cfg if isinstance(cfg, dict) else (json.loads(cfg) or {})
    except Exception as e:
        logger.error(f"Failed to load config for {plugin_name}: {e}")
        return {}


async def save_plugin_config(plugin_name: str, config: dict) -> None:
    """Upsert a plugin's persisted config overrides (JSONB)."""
    pool = await get_postgres_connection()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO plugin_configs (plugin_name, config, updated_at)
            VALUES ($1, $2::jsonb, NOW())
            ON CONFLICT (plugin_name) DO UPDATE SET
                config = EXCLUDED.config, updated_at = NOW()
            """,
            plugin_name,
            json.dumps(config),
        )
    logger.info(f"Saved config for plugin {plugin_name}: {list(config.keys())}")


async def save_plugin_manifest(plugin_name: str, manifest: dict) -> None:
    """Upsert a plugin's webhook manifest (JSONB) so its webhook route survives
    a registry restart (#269)."""
    try:
        pool = await get_postgres_connection()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO plugin_manifests (plugin_name, manifest, updated_at)
                VALUES ($1, $2::jsonb, NOW())
                ON CONFLICT (plugin_name) DO UPDATE SET
                    manifest = EXCLUDED.manifest, updated_at = NOW()
                """,
                plugin_name,
                json.dumps(manifest),
            )
        logger.debug(f"Saved manifest for plugin {plugin_name}")
    except Exception as e:
        logger.error(f"Failed to save manifest for {plugin_name}: {e}")
        # Same #351 bug class as update_plugin_in_database above, missed here: a
        # swallowed exception meant install_plugin's own try/except around
        # register_plugin_webhook (routes/plugins.py) could never actually fire
        # for THIS failure mode -- the in-memory webhook_routes/plugin_manifests
        # dicts were already updated (core/webhooks.py, before this call), so
        # the webhook worked immediately and the client got a 200 "installed
        # successfully" response, but nothing was persisted. On the next
        # registry restart, register_all_webhooks_on_startup() only restores
        # from what's actually in this table -- the webhook silently never came
        # back, indistinguishable from a healthy install via the API. Re-raise
        # so callers can convert it into an honest error (register_all_webhooks_
        # on_startup wraps its own per-plugin call in a try/except specifically
        # so this doesn't turn one transient DB hiccup during a REDUNDANT
        # restore-time re-write into the whole registry failing to start).
        raise


async def delete_plugin_from_database(plugin_name: str) -> None:
    """Hard-delete a plugin's persisted rows on uninstall (#639).

    Uninstall previously deleted only the in-memory state (plugins_db + the
    webhook_routes/plugin_manifests dicts), never the DB. On the next registry
    restart, ``load_plugins_from_database()`` re-loaded the plugin row (never
    deleted) and ``register_all_webhooks_on_startup()`` restored its webhook from
    the persisted manifest (also never deleted) — the "uninstalled" plugin fully
    resurrected, webhook and all. "Uninstall" means removal, so this hard-deletes
    the `plugins` row, its webhook `plugin_manifests` row, and any
    `plugin_configs` overrides, in one transaction. Re-adding the plugin then
    goes through registration again (from its on-disk manifest for a module
    plugin, or a fresh API register), which is the intended semantic.

    Only ever called from the uninstall path (routes/plugins.py). Disk-loaded
    module plugins (telegraf/network/…) still re-register from disk on the next
    boot regardless — that's correct, they ship in the repo; this deletion is
    about API/DB-registered plugins not silently coming back.
    """
    try:
        pool = await get_postgres_connection()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM plugins WHERE name = $1", plugin_name)
                await conn.execute(
                    "DELETE FROM plugin_manifests WHERE plugin_name = $1", plugin_name
                )
                await conn.execute(
                    "DELETE FROM plugin_configs WHERE plugin_name = $1", plugin_name
                )
        logger.info(f"Deleted plugin {plugin_name} from database (uninstall)")
    except Exception as e:
        logger.error(f"Failed to delete plugin {plugin_name} from database: {e}")
        # Re-raise (same #351 contract as the writes above) so uninstall can
        # report an honest error instead of a 200 that leaves the row behind to
        # resurrect on restart.
        raise


async def load_all_plugin_manifests() -> dict:
    """Load every persisted plugin manifest (plugin_name -> manifest dict), to
    restore webhook routes on startup (#269). {} on error — startup continues
    with no webhooks restored rather than failing."""
    try:
        pool = await get_postgres_connection()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT plugin_name, manifest FROM plugin_manifests"
            )
        manifests = {}
        for row in rows:
            manifest = row["manifest"]
            manifests[row["plugin_name"]] = (
                manifest if isinstance(manifest, dict) else json.loads(manifest)
            )
        return manifests
    except Exception as e:
        logger.error(f"Failed to load plugin manifests: {e}")
        return {}
