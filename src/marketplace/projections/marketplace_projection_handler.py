# src/marketplace/projections/marketplace_projection_handler.py

import json
import logging
from typing import Any, Dict

import psycopg2
import redis

from src.shared.projections.base_projection_handler import BaseProjectionHandler

logger = logging.getLogger(__name__)


class MarketplaceProjectionHandler(BaseProjectionHandler):
    """Marketplace read model updater - PostgreSQL + Redis dual write"""

    # Define routing keys for events this handler processes
    routing_keys = [
        "marketplace.pluginlisted",
        "marketplace.plugindelisted",
        "marketplace.licensepurchased",
        "marketplace.licenseexpired",
    ]

    def __init__(self, pg_url: str, redis_url: str, rabbitmq_url: str):
        super().__init__(rabbitmq_url)
        self.pg_url = pg_url
        self.redis_url = redis_url
        self._pg_conn = None
        self._redis_client = None

    def connect(self):
        """Connect to PostgreSQL and Redis"""
        # PostgreSQL connection
        if self._pg_conn is None or self._pg_conn.closed:
            self._pg_conn = psycopg2.connect(self.pg_url)

        # Redis connection
        if self._redis_client is None:
            self._redis_client = redis.from_url(self.redis_url, decode_responses=True)

    def _handle_pluginlisted(self, event_data: Dict[str, Any], is_replay: bool) -> None:
        """Update plugin catalog projection when plugin is listed"""
        self.connect()

        try:
            with self._pg_conn.cursor() as cursor:
                # Update PostgreSQL
                cursor.execute(
                    """
                    INSERT INTO plugin_catalog_projection (
                        id, name, developer_id, category, price,
                        description, is_listed, listed_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        category = EXCLUDED.category,
                        price = EXCLUDED.price,
                        description = EXCLUDED.description,
                        is_listed = EXCLUDED.is_listed,
                        listed_at = EXCLUDED.listed_at,
                        updated_at = EXCLUDED.updated_at
                """,
                    (
                        str(event_data["plugin_id"]),
                        event_data["plugin_name"],
                        str(event_data["developer_id"]),
                        event_data["category"],
                        event_data["price"],
                        event_data.get("description"),
                        True,
                        event_data["listing_date"],
                        event_data["listing_date"],
                    ),
                )

            self._pg_conn.commit()

            # Update Redis cache (TTL: 30s)
            redis_key = f"plugin:catalog:{event_data['plugin_id']}"
            cache_data = {
                "plugin_id": str(event_data["plugin_id"]),
                "name": event_data["plugin_name"],
                "category": event_data["category"],
                "price": str(event_data["price"]),
                "is_listed": True,
            }
            self._redis_client.setex(redis_key, 30, json.dumps(cache_data))

            logger.info(f"Updated plugin catalog for {event_data['plugin_name']}")

        except Exception as e:
            self._pg_conn.rollback()
            logger.error(f"Error handling PluginListed: {e}")
            raise

    def _handle_plugindelisted(self, event_data: Dict[str, Any], is_replay: bool) -> None:
        """Mark plugin as delisted in projection"""
        self.connect()

        try:
            with self._pg_conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE plugin_catalog_projection
                    SET is_listed = FALSE,
                        updated_at = %s
                    WHERE id = %s
                """,
                    (event_data["delisted_at"], str(event_data["plugin_id"])),
                )

            self._pg_conn.commit()

            # Invalidate Redis cache
            redis_key = f"plugin:catalog:{event_data['plugin_id']}"
            self._redis_client.delete(redis_key)

            logger.info(f"Delisted plugin {event_data['plugin_id']}")

        except Exception as e:
            self._pg_conn.rollback()
            logger.error(f"Error handling PluginDelisted: {e}")
            raise

    def _handle_licensepurchased(self, event_data: Dict[str, Any], is_replay: bool) -> None:
        """Update license projection when license is purchased"""
        self.connect()

        try:
            with self._pg_conn.cursor() as cursor:
                # Update PostgreSQL with license info
                cursor.execute(
                    """
                    INSERT INTO license_projection (
                        id, plugin_id, user_id, license_type,
                        expiry_date, purchase_date, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        plugin_id = EXCLUDED.plugin_id,
                        user_id = EXCLUDED.user_id,
                        license_type = EXCLUDED.license_type,
                        expiry_date = EXCLUDED.expiry_date,
                        purchase_date = EXCLUDED.purchase_date
                """,
                    (
                        str(event_data["license_id"]),
                        str(event_data["plugin_id"]),
                        str(event_data["user_id"]),
                        event_data["license_type"],
                        event_data.get("expiry_date"),
                        event_data["purchase_date"],
                        event_data["purchase_date"],
                    ),
                )

            self._pg_conn.commit()

            # Update Redis cache
            redis_key = f"license:{event_data['license_id']}"
            cache_data = {
                "license_id": str(event_data["license_id"]),
                "plugin_id": str(event_data["plugin_id"]),
                "user_id": str(event_data["user_id"]),
                "license_type": event_data["license_type"],
                "expiry_date": str(event_data.get("expiry_date")),
            }
            self._redis_client.setex(redis_key, 60, json.dumps(cache_data))  # 1 minute TTL for licenses

            logger.info(f"Recorded license purchase {event_data['license_id']}")

        except Exception as e:
            self._pg_conn.rollback()
            logger.error(f"Error handling LicensePurchased: {e}")
            raise

    def _handle_licenseexpired(self, event_data: Dict[str, Any], is_replay: bool) -> None:
        """Mark license as expired in projection"""
        self.connect()

        try:
            with self._pg_conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE license_projection
                    SET is_expired = TRUE,
                        expired_at = %s
                    WHERE id = %s
                """,
                    (event_data["expiry_date"], str(event_data["license_id"])),
                )

            self._pg_conn.commit()

            # Invalidate Redis cache
            redis_key = f"license:{event_data['license_id']}"
            self._redis_client.delete(redis_key)

            logger.info(f"Marked license {event_data['license_id']} as expired")

        except Exception as e:
            self._pg_conn.rollback()
            logger.error(f"Error handling LicenseExpired: {e}")
            raise
