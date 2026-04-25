"""
Minder Database Migration Manager
Handles plugin database creation, migrations, and backup/restore
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import asyncpg

logger = logging.getLogger(__name__)


@dataclass
class MigrationRecord:
    """Migration record"""

    version: str
    name: str
    applied_at: datetime
    execution_time_ms: int
    success: bool


class DatabaseMigrationManager:
    """
    Database migration manager for plugins

    Features:
    - Automatic database creation
    - Migration version tracking
    - Rollback support
    - Backup/restore functionality
    """

    def __init__(self, connection_pool: asyncpg.Pool = None):
        self.connection_pool = connection_pool
        self.logger = logging.getLogger(__name__)

    async def create_plugin_database(
        self, plugin_id: str, db_config: Dict, migrations_dir: str = "/migrations"
    ) -> Dict:
        """
        Create database for plugin

        Args:
            plugin_id: Plugin identifier
            db_config: Database configuration
            migrations_dir: Path to migration files

        Returns:
            Result dict
        """
        result = {"success": False, "database_name": None, "errors": []}

        try:
            # Connect to postgres database (default)
            admin_conn = await asyncpg.connect(
                host=db_config.get("host", "localhost"),
                port=db_config.get("port", 5432),
                database="postgres",  # Connect to default db
                user=db_config.get("user", "postgres"),
                password=db_config.get("password", ""),
            )

            # Database name
            db_name = db_config.get("database", f"{plugin_id}_db")
            result["database_name"] = db_name

            # Check if database exists
            exists = await admin_conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db_name)

            if exists:
                self.logger.info(f"✅ Database {db_name} already exists")
            else:
                # Create database
                await admin_conn.execute(
                    f'CREATE DATABASE "{db_name}" '
                    f"ENCODING 'UTF8' "
                    f"LC_COLLATE='en_US.UTF-8' "
                    f"LC_CTYPE='en_US.UTF-8'"
                )
                self.logger.info(f"✅ Created database: {db_name}")

            # Close admin connection
            await admin_conn.close()

            # Connect to new database
            conn = await asyncpg.connect(
                host=db_config.get("host", "localhost"),
                port=db_config.get("port", 5432),
                database=db_name,
                user=db_config.get("user", "postgres"),
                password=db_config.get("password", ""),
            )

            # Create migrations table
            await self._create_migrations_table(conn)

            # Run initial migrations
            migrations_path = Path(migrations_dir)
            if migrations_path.exists():
                await self.run_migrations(plugin_id, conn, str(migrations_path))

            await conn.close()

            result["success"] = True
            return result

        except Exception as e:
            self.logger.error(f"❌ Failed to create database for {plugin_id}: {e}")
            result["errors"].append(str(e))
            return result

    async def _create_migrations_table(self, conn: asyncpg.Connection):
        """Create migrations tracking table"""
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS _migrations (
                id SERIAL PRIMARY KEY,
                version VARCHAR(255) NOT NULL UNIQUE,
                name VARCHAR(255) NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                execution_time_ms INTEGER,
                success BOOLEAN DEFAULT TRUE
            )
        """
        )
        self.logger.info("✅ Migrations table created/verified")

    async def run_migrations(
        self, plugin_id: str, conn: asyncpg.Connection, migrations_dir: str
    ) -> List[MigrationRecord]:
        """
        Run database migrations

        Args:
            plugin_id: Plugin identifier
            conn: Database connection
            migrations_dir: Path to migration files

        Returns:
            List of migration records
        """
        migrations_path = Path(migrations_dir)
        if not migrations_path.exists():
            self.logger.warning(f"⚠️ Migrations directory not found: {migrations_dir}")
            return []

        # Get applied migrations
        applied = await conn.fetch("SELECT version FROM _migrations ORDER BY applied_at")
        applied_versions = {row["version"] for row in applied}

        # Find migration files (sorted)
        migration_files = sorted(migrations_path.glob("*.sql"))

        records = []
        for migration_file in migration_files:
            # Extract version from filename (e.g., 001_initial.sql -> 001)
            version = migration_file.stem.split("_")[0]

            if version in applied_versions:
                self.logger.info(f"⊘ Migration {version} already applied, skipping")
                continue

            # Read migration SQL
            with open(migration_file, "r") as f:
                migration_sql = f.read()

            # Execute migration
            start_time = datetime.utcnow()
            try:
                await conn.execute(migration_sql)

                # Record migration
                execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)

                await conn.execute(
                    """
                    INSERT INTO _migrations (version, name, applied_at, execution_time_ms, success)
                    VALUES ($1, $2, $3, $4, TRUE)
                    """,
                    version,
                    migration_file.name,
                    start_time,
                    execution_time,
                )

                record = MigrationRecord(
                    version=version,
                    name=migration_file.name,
                    applied_at=start_time,
                    execution_time_ms=execution_time,
                    success=True,
                )
                records.append(record)

                self.logger.info(f"✅ Applied migration: {version}")

            except Exception as e:
                self.logger.error(f"❌ Migration {version} failed: {e}")

                # Record failed migration
                await conn.execute(
                    """
                    INSERT INTO _migrations (version, name, applied_at, execution_time_ms, success)
                    VALUES ($1, $2, $3, $4, FALSE)
                    """,
                    version,
                    migration_file.name,
                    start_time,
                    0,
                )

                record = MigrationRecord(
                    version=version,
                    name=migration_file.name,
                    applied_at=start_time,
                    execution_time_ms=0,
                    success=False,
                )
                records.append(record)

        return records

    async def backup_database(self, plugin_id: str, db_config: Dict, backup_path: str = None) -> Dict:
        """
        Backup plugin database

        Args:
            plugin_id: Plugin identifier
            db_config: Database configuration
            backup_path: Path for backup file

        Returns:
            Result dict
        """
        result = {"success": False, "backup_file": None, "errors": []}

        try:
            import subprocess

            db_name = db_config.get("database", f"{plugin_id}_db")

            # Generate backup filename
            if not backup_path:
                backup_dir = Path("/var/lib/minder/backups")
                backup_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                backup_path = backup_dir / f"{plugin_id}_{timestamp}.sql"

            # Use pg_dump for backup
            cmd = [
                "pg_dump",
                "-h",
                db_config.get("host", "localhost"),
                "-p",
                str(db_config.get("port", 5432)),
                "-U",
                db_config.get("user", "postgres"),
                "-d",
                db_name,
                "-f",
                str(backup_path),
                "--no-owner",
                "--no-acl",
            ]

            # Set password environment variable
            import os

            env = os.environ.copy()
            env["PGPASSWORD"] = db_config.get("password", "")

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                result["success"] = True
                result["backup_file"] = str(backup_path)
                self.logger.info(f"✅ Database backup created: {backup_path}")
            else:
                result["errors"].append(stderr.decode())
                self.logger.error(f"❌ Backup failed: {stderr.decode()}")

            return result

        except Exception as e:
            self.logger.error(f"❌ Backup failed: {e}")
            result["errors"].append(str(e))
            return result

    async def restore_database(self, plugin_id: str, db_config: Dict, backup_path: str) -> Dict:
        """
        Restore plugin database from backup

        Args:
            plugin_id: Plugin identifier
            db_config: Database configuration
            backup_path: Path to backup file

        Returns:
            Result dict
        """
        result = {"success": False, "errors": []}

        try:
            import subprocess

            db_name = db_config.get("database", f"{plugin_id}_db")

            # Use psql for restore
            cmd = [
                "psql",
                "-h",
                db_config.get("host", "localhost"),
                "-p",
                str(db_config.get("port", 5432)),
                "-U",
                db_config.get("user", "postgres"),
                "-d",
                db_name,
                "-f",
                backup_path,
            ]

            # Set password environment variable
            import os

            env = os.environ.copy()
            env["PGPASSWORD"] = db_config.get("password", "")

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                result["success"] = True
                self.logger.info(f"✅ Database restored from: {backup_path}")
            else:
                result["errors"].append(stderr.decode())
                self.logger.error(f"❌ Restore failed: {stderr.decode()}")

            return result

        except Exception as e:
            self.logger.error(f"❌ Restore failed: {e}")
            result["errors"].append(str(e))
            return result

    async def get_migration_history(self, plugin_id: str, conn: asyncpg.Connection) -> List[Dict]:
        """
        Get migration history for plugin

        Args:
            plugin_id: Plugin identifier
            conn: Database connection

        Returns:
            List of migration records
        """
        try:
            rows = await conn.fetch(
                """
                SELECT version, name, applied_at, execution_time_ms, success
                FROM _migrations
                ORDER BY applied_at DESC
                """
            )

            return [dict(row) for row in rows]

        except Exception as e:
            self.logger.error(f"❌ Failed to get migration history: {e}")
            return []

    async def create_plugin_user(
        self, plugin_id: str, db_config: Dict, username: str = None, password: str = None
    ) -> Dict:
        """
        Create database user for plugin

        Args:
            plugin_id: Plugin identifier
            db_config: Database configuration
            username: Username (defaults to plugin_id)
            password: Password (auto-generated if not provided)

        Returns:
            Result dict
        """
        result = {"success": False, "username": None, "errors": []}

        try:
            if not username:
                username = f"{plugin_id}_user"

            if not password:
                import secrets

                password = secrets.token_urlsafe(32)

            # Connect to postgres database
            conn = await asyncpg.connect(
                host=db_config.get("host", "localhost"),
                port=db_config.get("port", 5432),
                database="postgres",
                user=db_config.get("user", "postgres"),
                password=db_config.get("password", ""),
            )

            # Create user
            await conn.execute(
                f"""
                CREATE USER "{username}" WITH PASSWORD '{password}'
            """
            )

            # Grant privileges on plugin database
            db_name = db_config.get("database", f"{plugin_id}_db")
            await conn.execute(
                f"""
                GRANT ALL PRIVILEGES ON DATABASE "{db_name}" TO "{username}"
            """
            )

            await conn.close()

            result["success"] = True
            result["username"] = username
            result["password"] = password

            self.logger.info(f"✅ Created database user: {username}")

            return result

        except Exception as e:
            self.logger.error(f"❌ Failed to create user: {e}")
            result["errors"].append(str(e))
            return result


if __name__ == "__main__":
    # Test migration manager
    async def test():
        manager = DatabaseMigrationManager()

        db_config = {"host": "localhost", "port": 5432, "user": "postgres", "password": "postgres"}

        result = await manager.create_plugin_database(
            "test_plugin", db_config, "/root/minder/plugins/weather/migrations"
        )

        print(f"Result: {result}")

    asyncio.run(test())
