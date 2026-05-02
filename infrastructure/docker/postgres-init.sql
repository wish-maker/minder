-- Minder Platform - PostgreSQL Initialization Script
-- Created: Automatically by deploy.sh

-- Create additional databases
DO $$ BEGIN
    CREATE DATABASE tefas_db;
EXCEPTION
    WHEN duplicate_database THEN NULL;
END $$;

DO $$ BEGIN
    CREATE DATABASE weather_db;
EXCEPTION
    WHEN duplicate_database THEN NULL;
END $$;

DO $$ BEGIN
    CREATE DATABASE news_db;
EXCEPTION
    WHEN duplicate_database THEN NULL;
END $$;

DO $$ BEGIN
    CREATE DATABASE crypto_db;
EXCEPTION
    WHEN duplicate_database THEN NULL;
END $$;

DO $$ BEGIN
    CREATE DATABASE minder_marketplace;
EXCEPTION
    WHEN duplicate_database THEN NULL;
END $$;

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
