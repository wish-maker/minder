# Minder Quick Start Guide

Get up and running with Minder in 5 minutes.

## Prerequisites

- Docker & Docker Compose
- 8GB+ RAM recommended
- Python 3.11+ (for local development or if Docker containers have issues)

**Note:** If you encounter issues with the Docker containers, you can run the API directly using Python locally after installing dependencies.

## Installation

### 1. Clone and Start

```bash
# Clone the repository
git clone https://github.com/wish-maker/minder.git
cd minder

# Copy environment template
cp .env.example .env

# Edit .env with your configuration
nano .env  # or use your preferred editor

# Start all services
docker compose up -d

# Check status
docker compose ps
```

Expected output: All services showing "Up" status

### 2. Verify Installation

```bash
# Check if containers are running
docker compose ps

# Wait for all services to be healthy (may take 1-2 minutes)
# Health check
curl http://localhost:8000/health

# Expected response:
# {"status":"healthy","version":"2.0.0","plugins_active":5}

# If the API is not responding, check logs:
docker compose logs -f minder-api
```

### 3. Login and Get Token

```bash
# Authenticate
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'

# Save the token from response
export TOKEN="paste_your_token_here"
```

### 4. Explore Plugins

```bash
# List all plugins
curl http://localhost:8000/plugins \
  -H "Authorization: Bearer $TOKEN"

# Expected response:
# {
#   "plugins": [
#     {"name": "tefas", "version": "1.0.0", "status": "active"},
#     {"name": "crypto", "version": "1.0.0", "status": "active"},
#     ...
#   ],
#   "total": 5
# }
```

### 5. Run Plugin Pipeline

```bash
# Run TEFAS fund analysis pipeline
curl -X POST http://localhost:8000/plugins/tefas/pipeline \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pipeline": ["collect", "analyze", "train"]}'

# Expected response:
# {"status": "success", "records_processed": 15}
```

## Next Steps

- **Explore the API**: Visit http://localhost:8000/docs for interactive documentation
- **Read Architecture**: Check [Architecture Overview](../architecture/overview.md)
- **Develop Plugins**: Follow [Plugin Development Guide](plugin-development.md)
- **Deploy**: See [Deployment Guide](deployment.md)

## Troubleshooting

**Port already in use?**
```bash
# Check what's using port 8000
lsof -i :8000
# Change port in docker-compose.yml if needed
```

**Containers not starting?**
```bash
# Check logs
docker compose logs minder-api

# Rebuild containers
docker compose down
docker compose build
docker compose up -d
```

**Can't authenticate?**
```bash
# Reset admin password
docker exec -it minder-api python -c "
from api.auth import hash_password
print(hash_password('admin123'))
"
# Update the hash in PostgreSQL
```

**Environment variables missing?**
```bash
# Ensure .env file exists
cp .env.example .env

# Edit with your values
nano .env

# Restart services
docker compose down
docker compose up -d
```

**API container not starting?**
```bash
# If the Docker container has issues, you can run the API locally:

# Install dependencies locally
pip install -r requirements.txt

# Set environment variables
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export REDIS_HOST=localhost
# ... (set other variables from .env)

# Run the API directly
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```