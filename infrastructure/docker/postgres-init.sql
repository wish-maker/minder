-- Minder Platform - PostgreSQL Initialization Script
-- Created: Automatically by deploy.sh

-- Create additional databases
CREATE DATABASE IF NOT EXISTS tefas_db;
CREATE DATABASE IF NOT EXISTS weather_db;
CREATE DATABASE IF NOT EXISTS news_db;
CREATE DATABASE IF NOT EXISTS crypto_db;
CREATE DATABASE IF NOT EXISTS minder_marketplace;

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
