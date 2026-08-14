"""
Plugin health monitoring and background schedulers.

Holds the startup service-cache restore, the periodic plugin health-check loop,
the auto-enable-on-startup routine and the hourly data-collection scheduler.
These operate on the shared caches in ``core.state`` and persist status changes
via ``core.database``.
"""

import asyncio
import json
from datetime import datetime, timezone

from core.database import update_plugin_in_database
from core.state import logger, plugin_instances, plugins_db, redis_client, services_db
from models import ServiceRegistration

from config import settings


async def load_services_from_redis():
    """Load registered services from Redis into memory cache"""
    try:
        # Get all service keys from Redis
        service_keys = redis_client.keys("service:*")

        if not service_keys:
            logger.info("No services found in Redis")
            return

        loaded_count = 0

        for service_key in service_keys:
            try:
                # Extract service name from key (format: service:service_name)
                service_name = service_key.replace("service:", "")

                # Get service data from Redis hash
                service_data = redis_client.hgetall(service_key)

                if not service_data:
                    logger.warning(f"Service data empty for {service_name}")
                    continue

                # Parse service data
                service_registration = ServiceRegistration(
                    service_name=service_name,
                    service_type=service_data.get("service_type", "unknown"),
                    host=service_data.get("host", "unknown"),
                    port=int(service_data.get("port", 0)),
                    health_check_url=service_data.get("health_check_url", "/health"),
                    metadata=json.loads(service_data.get("metadata", "{}")),
                )

                services_db[service_name] = service_registration
                loaded_count += 1

            except Exception as e:
                logger.error(f"Failed to load service {service_key}: {e}")

        logger.info(f"✅ Loaded {loaded_count} services from Redis into memory")

    except Exception as e:
        logger.error(f"❌ Failed to load services from Redis: {e}")
        raise


async def health_check_loop():
    """Background task to monitor plugin health"""
    while True:
        # Snapshot the dict: health_check() below awaits, so a concurrent plugin
        # uninstall (del plugin_instances[name]) would otherwise raise
        # "dictionary changed size during iteration" — which, being raised by the
        # for-statement rather than the per-plugin try/except, would escape the
        # while-loop and permanently kill health monitoring (the task ref is lost).
        for plugin_name, plugin_instance in list(plugin_instances.items()):
            try:
                health = await plugin_instance.health_check()
                plugin_info = plugins_db.get(plugin_name)

                if plugin_info:
                    plugin_info.health_status = (
                        "healthy" if health.get("healthy") else "unhealthy"
                    )
                    last_check_dt = datetime.now(timezone.utc)
                    plugin_info.last_health_check = last_check_dt.isoformat()

                    # Update in Redis for service discovery
                    redis_client.hset(
                        f"plugin:{plugin_name}",
                        mapping={
                            "health_status": plugin_info.health_status,
                            "last_health_check": plugin_info.last_health_check,
                        },
                    )

                    # Update in PostgreSQL for persistence (pass datetime object, not string)
                    await update_plugin_in_database(
                        plugin_name,
                        health_status=plugin_info.health_status,
                        last_health_check=last_check_dt,
                    )

            except Exception as e:
                logger.error(f"Health check failed for {plugin_name}: {e}")
                if plugin_name in plugins_db:
                    plugins_db[plugin_name].health_status = "error"

        await asyncio.sleep(settings.HEALTH_CHECK_INTERVAL_SECONDS)


async def auto_enable_plugins():
    """Automatically enable all plugins on startup"""
    logger.info("Auto-enabling all plugins...")

    for plugin_name, plugin_info in plugins_db.items():
        # #351: persist BEFORE mutating in-memory state -- matches the fix already
        # applied to routes/plugins.py's enable_plugin. A DB failure here used to be
        # silently swallowed while in-memory state already said "enabled," leaving
        # the two out of sync until the next restart reloaded from DB.
        try:
            await update_plugin_in_database(plugin_name, enabled=True, status="enabled")
        except Exception as e:
            logger.error(f"❌ Failed to auto-enable {plugin_name}: {e}")
            continue
        plugin_info.enabled = True
        plugin_info.status = "enabled"
        logger.info(f"✅ Auto-enabled plugin: {plugin_name}")


async def data_collection_scheduler():
    """Automatically trigger data collection for all enabled plugins every hour"""
    while True:
        try:
            # Wait 1 hour (3600 seconds)
            await asyncio.sleep(3600)

            logger.info("🔄 Scheduled data collection starting...")

            # Collect data from all enabled plugins
            for plugin_name, plugin_info in plugins_db.items():
                if plugin_info.enabled and plugin_name in plugin_instances:
                    try:
                        plugin_instance = plugin_instances[plugin_name]

                        # Trigger data collection
                        result = await plugin_instance.collect_data()

                        logger.info(
                            f"✅ {plugin_name}: {result.get('records_collected', 0)} records collected"
                        )
                    except Exception as e:
                        logger.error(f"❌ {plugin_name}: Collection failed - {e}")

            logger.info("✅ Scheduled data collection complete")

        except Exception as e:
            logger.error(f"❌ Data collection scheduler error: {e}")
            # Wait 5 minutes before retry
            await asyncio.sleep(300)
