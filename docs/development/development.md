# Development Guide

## Overview

This guide covers local development setup, workflow, and best practices for contributing to Minder Platform.

## Prerequisites

### Required Software

- **Python** 3.11+ - Core runtime
- **Docker** 20.10+ - Container runtime
- **Docker Compose** 2.20+ - Service orchestration
- **Git** - Version control
- **VS Code** or **PyCharm** - Recommended IDE

### Recommended Tools

- **Postman** or **curl** - API testing
- **pgAdmin** - Database management
- **Redis Insight** - Redis GUI
- **make** - Build automation

## Local Development Setup

### Quick Start

```bash
# Clone repository
git clone https://github.com/wish-maker/minder.git
cd minder

# Run setup
./setup.sh

# Verify installation
./scripts/health-check.sh
```

### Manual Setup

#### Step 1: Environment Configuration

```bash
# Create environment file
cp infrastructure/docker/.env.example infrastructure/docker/.env

# Generate secure passwords
POSTGRES_PASSWORD=$(openssl rand -base64 32)
REDIS_PASSWORD=$(openssl rand -base64 32)
JWT_SECRET=$(openssl rand -base64 64)
INFLUXDB_TOKEN=$(openssl rand -base64 32)

# Update .env file
cat >> infrastructure/docker/.env << EOF
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
REDIS_PASSWORD=$REDIS_PASSWORD
JWT_SECRET=$JWT_SECRET
INFLUXDB_TOKEN=$INFLUXDB_TOKEN
ENVIRONMENT=development
LOG_LEVEL=DEBUG
EOF
```

#### Step 2: Start Infrastructure

```bash
# Start databases and core services
docker compose -f infrastructure/docker/docker-compose.yml up -d postgres redis qdrant ollama neo4j

# Wait for services to be ready
sleep 30
```

#### Step 3: Start Application Services

```bash
# Start security layer
docker compose -f infrastructure/docker/docker-compose.yml up -d traefik authelia

# Start core APIs
docker compose -f infrastructure/docker/docker-compose.yml up -d api-gateway plugin-registry marketplace plugin-state-manager

# Start AI services
docker compose -f infrastructure/docker/docker-compose.yml up -d rag-pipeline model-management

# Start AI enhancement and monitoring
docker compose -f infrastructure/docker/docker-compose.yml up -d openwebui tts-stt-service model-fine-tuning prometheus grafana
```

#### Step 4: Verify Setup

```bash
# Health check
./scripts/health-check.sh

# Run tests (118 passing, 93% coverage)
pytest tests/unit/ -v
```

## Development Workflow

### 1. Feature Development

```bash
# Create feature branch
git checkout -b feature/new-plugin-system

# Make changes
# ... code changes ...

# Test changes
pytest tests/unit/ -v

# Commit changes
git add .
git commit -m "Add new plugin system"
```

### 2. Service Development

#### Adding a New Service

```bash
# Create service directory
mkdir services/new-service
cd services/new-service

# Create service structure
touch main.py config.py Dockerfile requirements.txt

# Implement service
# ... write code ...

# Add to docker-compose.yml
# Add service definition

# Build and test
docker compose -f infrastructure/docker/docker-compose.yml up -d --build new-service
```

#### Service Template

```python
# main.py
from fastapi import FastAPI
from .config import settings

app = FastAPI(title="New Service", version="1.0.0")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "new-service"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8008)
```

### 3. Testing

#### Run Tests

```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# With coverage
pytest tests/ --cov=src --cov-report=html

# Specific test file
pytest tests/unit/test_rate_limiter.py -v

# Watch mode (auto-rerun on changes)
pytest tests/unit/ -f
```

#### Write Tests

```python
# tests/unit/test_example.py
import pytest
from src.shared.validators import validate_plugin_name

def test_valid_plugin_name():
    assert validate_plugin_name("my-plugin") == True
    
def test_invalid_plugin_name():
    assert validate_plugin_name("invalid name!") == False
```

### 4. Code Quality

#### Type Checking

```bash
# Run mypy
mypy src/

# Check specific module
mypy src/shared/validators.py
```

#### Linting

```bash
# Run ruff linter
ruff check src/

# Auto-fix issues
ruff check --fix src/

# Format code
ruff format src/
```

#### Import Sorting

```bash
# Sort imports
isort src/

# Check import sorting
isort --check-only src/
```

## Service-Specific Development

### API Gateway Development

```bash
# Enter container
docker exec -it minder-api-gateway bash

# Install dependencies
pip install new-package

# Update requirements.txt
pip freeze > requirements.txt

# Rebuild container
docker compose -f infrastructure/docker/docker-compose.yml build api-gateway
docker compose -f infrastructure/docker/docker-compose.yml up -d api-gateway
```

### Database Development

```bash
# Connect to PostgreSQL
docker exec -it minder-postgres psql -U minder

# View databases
\l

# Connect to specific database
\c minder

# View tables
\dt

# Run queries
SELECT * FROM plugins LIMIT 10;
```

### Redis Development

```bash
# Connect to Redis
docker exec -it minder-redis redis-cli -a ${REDIS_PASSWORD}

# View keys
KEYS *

# Get value
GET key:plugin:123

# Monitor commands
MONITOR
```

## Debugging

### View Logs

```bash
# All services
docker compose -f infrastructure/docker/docker-compose.yml logs -f

# Specific service
docker logs minder-api-gateway -f

# Last 100 lines
docker logs minder-api-gateway --tail 100

# Since specific time
docker logs minder-api-gateway --since 1h
```

### Enter Container

```bash
# Enter shell
docker exec -it minder-api-gateway bash

# Debug with Python
docker exec -it minder-api-gateway python -m pdb main.py
```

### Performance Profiling

```bash
# Check resource usage
docker stats

# Profile service
docker exec minder-api-gateway python -m cProfile -o profile.stats main.py

# View stats
docker exec minder-api-gateway python -m pstats profile.stats
```

## Hot Reload

### Development with Auto-Reload

For local development without Docker:

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run with auto-reload
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Docker Compose Auto-Reload

```yaml
# In docker-compose.yml
services:
  api-gateway:
    volumes:
      - ./services/api-gateway:/app
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Common Development Tasks

### Add New API Endpoint

```python
# In services/api-gateway/routes/plugins.py
from fastapi import APIRouter, HTTPException
from loguru import logger

router = APIRouter(prefix="/api/v1/plugins", tags=["plugins"])

@router.post("/")
async def create_plugin(plugin: PluginCreate):
    logger.info(f"Creating plugin: {plugin.name}")
    # Implementation here
    return {"id": "123", "status": "created"}
```

### Add Database Migration

```sql
# In migrations/001_add_new_table.sql
CREATE TABLE new_table (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Run migration
docker exec -i minder-postgres psql -U minder < migrations/001_add_new_table.sql
```

### Update Dependencies

```bash
# Update specific dependency
pip install --upgrade fastapi

# Update requirements.txt
pip freeze > requirements.txt

# Rebuild container
docker compose -f infrastructure/docker/docker-compose.yml build <service>
```

## Git Workflow

### Branch Strategy

```
main (production)
  └── develop (staging)
      ├── feature/new-plugin
      ├── feature/refactor-api
      └── bugfix/fix-rate-limiter
```

### Commit Conventions

```
feat: add new plugin registration endpoint
fix: resolve rate limiter memory leak
docs: update architecture documentation
refactor: simplify database connection pooling
test: add integration tests for marketplace
chore: update dependencies
```

### Pull Request Process

1. Create feature branch
2. Make changes and commit
3. Run tests: `pytest tests/unit/ -v`
4. Run linting: `ruff check src/`
5. Push to GitHub
6. Create pull request
7. Request review
8. Address feedback
9. Merge to main

## Code Review Guidelines

### What to Check

- [ ] Code follows PEP 8 style guide
- [ ] Tests added for new features
- [ ] Documentation updated
- [ ] No hardcoded credentials
- [ ] Error handling implemented
- [ ] Performance considered
- [ ] Security implications reviewed

### Review Checklist

- [ ] Clear commit message
- [ ] Focused changes (one feature per PR)
- [ ] Tests pass locally
- [ ] No merge conflicts
- [ ] Backwards compatible
- [ ] Documentation complete

## Performance Optimization

### Database Queries

```python
# Bad: N+1 queries
for plugin in plugins:
    tags = db.query(Tag).filter(Tag.plugin_id == plugin.id).all()

# Good: Single query with join
plugins = db.query(Plugin).options(joinedload(Tag)).all()
```

### Caching Strategy

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def get_plugin_config(plugin_id: str):
    return db.query(Plugin).filter(Plugin.id == plugin_id).first()
```

### Async Operations

```python
import asyncio

async def fetch_multiple_services():
    tasks = [
        fetch_service_a(),
        fetch_service_b(),
        fetch_service_c()
    ]
    results = await asyncio.gather(*tasks)
    return results
```

## Security Best Practices

### Input Validation

```python
from pydantic import BaseModel, validator

class PluginCreate(BaseModel):
    name: str
    version: str
    
    @validator('name')
    def validate_name(cls, v):
        if not v or len(v) > 100:
            raise ValueError('Invalid plugin name')
        return v
```

### SQL Injection Prevention

```python
# Bad: String concatenation
query = f"SELECT * FROM plugins WHERE name = '{name}'"

# Good: Parameterized queries
query = "SELECT * FROM plugins WHERE name = %s"
cursor.execute(query, (name,))
```

### Secrets Management

```python
import os
from cryptography.fernet import Fernet

# Load secret from environment
secret_key = os.getenv('ENCRYPTION_KEY')

# Use for encryption
f = Fernet(secret_key)
encrypted = f.encrypt(data)
```

## Troubleshooting

### Common Issues

**Import Errors**:
```bash
# Check Python path
python -c "import sys; print('\n'.join(sys.path))"

# Install missing dependency
pip install missing-package
```

**Database Connection Errors**:
```bash
# Check database is running
docker exec minder-postgres pg_isready -U minder

# Check connection string
cat infrastructure/docker/.env | grep POSTGRES
```

**Port Already in Use**:
```bash
# Find process using port
lsof -i :8000

# Kill process
kill -9 <PID>
```

## Resources

### Documentation

- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Docker Compose](https://docs.docker.com/compose/)
- [Pydantic](https://docs.pydantic.dev/)
- [pytest](https://docs.pytest.org/)

### Internal Documentation

- `docs/ARCHITECTURE.md` - System design
- `docs/API.md` - API documentation
- `docs/TROUBLESHOOTING.md` - Common issues

### Getting Help

- GitHub Issues: https://github.com/wish-maker/minder/issues
- Slack Channel: #minder-dev
- Email: dev@minder-platform.com

## Best Practices Summary

1. **Write Tests**: Maintain >90% test coverage
2. **Document Code**: Complex logic needs comments
3. **Use Type Hints**: Improve code clarity
4. **Follow PEP 8**: Consistent code style
5. **Security First**: Validate all inputs
6. **Performance**: Profile before optimizing
7. **Git Hygiene**: Clear commit messages
8. **Code Review**: All changes reviewed
9. **Backup Often**: Don't lose work
10. **Stay Updated**: Keep dependencies current
