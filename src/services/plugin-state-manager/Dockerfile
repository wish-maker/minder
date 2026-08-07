# src/services/plugin-state-manager/Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY src/services/plugin-state-manager/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --timeout 600 --retries 5 -r requirements.txt || \
    pip install --no-cache-dir --timeout 600 --retries 5 -r requirements.txt

# Copy application code -- only this service's own files + the shared library it
# actually imports (shared.config/db/errors/health/log/metrics/models/pagination/
# utils.cors -- confirmed via grep, no other service's code or src/plugins is ever
# imported). Was previously COPY src/services/ + COPY src/ wholesale, sweeping every
# other service's routes/core/schema.sql/requirements.txt and src/plugins into this
# one image for no reason -- a container compromise here would have leaked the
# entire backend source tree instead of just this service's own.
COPY src/services/plugin-state-manager/main.py .
COPY src/services/plugin-state-manager/config.py .
COPY src/services/plugin-state-manager/schema.sql .
COPY src/services/plugin-state-manager/models ./models
COPY src/services/plugin-state-manager/routes ./routes
COPY src/services/plugin-state-manager/core ./core
COPY src/shared /app/src/shared

# Create user
RUN useradd -m -u 1000 state-manager && chown -R state-manager:state-manager /app

USER state-manager

# Expose port
EXPOSE 8003

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8003/health || exit 1

# Run application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]
