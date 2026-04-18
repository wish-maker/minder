# Minder Production Deployment Guide

## Overview

Minder is a modular RAG platform with hot-swappable plugins, designed for production deployment with enterprise-grade security, monitoring, and scalability.

## Quick Start

### 1. Configure Environment
```bash
cp .env.example .env
nano .env  # Edit with secure values
```

### 2. Run Setup
```bash
bash scripts/setup_environment.sh
```

### 3. Deploy
```bash
# Development
docker compose up -d

# Production
bash scripts/deploy_production.sh
```

## Monitoring

```bash
# System metrics
python3 scripts/monitoring_cli.py system

# API performance
python3 scripts/monitoring_cli.py api

# All metrics
python3 scripts/monitoring_cli.py all
```

## Backup & Recovery

```bash
# Backup
bash scripts/backup_databases.sh

# Restore
bash scripts/restore_databases.sh /path/to/backup.tar.gz
```

## Health Checks

```bash
curl http://localhost:8000/health
curl http://localhost:8000/system/status
```

## Support

- API Docs: http://localhost:8000/docs
- GitHub: https://github.com/wish-maker/minder/issues
