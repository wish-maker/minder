-- Minder Platform - PostgreSQL Initialization Script
-- Created: Automatically by deploy.sh

-- Create additional databases (idempotent via psql \gexec).
-- NOTE: CREATE DATABASE cannot run inside a DO/PL-pgSQL block ("CREATE DATABASE cannot
-- run inside a transaction block"), so the previous "DO $$ ... EXCEPTION WHEN
-- duplicate_database $$" form always errored and, under the postgres entrypoint's
-- ON_ERROR_STOP=1, aborted the rest of this script (extensions/schemas/grants never ran,
-- and none of these DBs were created). \gexec runs each generated statement OUTSIDE a
-- transaction; the NOT EXISTS guard makes it idempotent.
SELECT 'CREATE DATABASE tefas_db'              WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'tefas_db')\gexec
SELECT 'CREATE DATABASE weather_db'            WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'weather_db')\gexec
SELECT 'CREATE DATABASE news_db'               WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'news_db')\gexec
SELECT 'CREATE DATABASE crypto_db'             WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'crypto_db')\gexec
SELECT 'CREATE DATABASE minder_marketplace'    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'minder_marketplace')\gexec
SELECT 'CREATE DATABASE minder_authelia'       WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'minder_authelia')\gexec
-- Dedicated DB for Apicurio schema-registry. It shares the Postgres server with Open
-- WebUI, and both define a `config` table with incompatible columns. In the shared
-- `minder` DB, Open WebUI's `config` pre-existed and apicurio's bootstrap DDL aborted on
-- it before creating `artifactreferences` -> DELETE 500s. Its own DB removes the collision.
SELECT 'CREATE DATABASE minder_schemaregistry' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'minder_schemaregistry')\gexec

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create schemas
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS plugins;
CREATE SCHEMA IF NOT EXISTS users;
CREATE SCHEMA IF NOT EXISTS metrics;

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public, core, plugins, users, metrics TO minder;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public, core, plugins, users, metrics TO minder;
