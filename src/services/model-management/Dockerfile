FROM python:3.12-slim

WORKDIR /app

# Set Python environment
ENV PYTHONPATH=/app:$PYTHONPATH
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies. apt-get upgrade pulls in Debian security
# patches already available for base-image packages (e.g. util-linux's
# CVE fixes) that the pinned python:3.12-slim layer predates.
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY src/services/model-management/requirements.txt .

# pip itself (bundled with python:3.12-slim) ships a version with known CVEs
# (e.g. CVE-2026-8643) that predate this Dockerfile -- bump before installing
# any requirements, as its own cacheable layer.
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir --timeout 600 --retries 5 -r requirements.txt || \
    pip install --no-cache-dir --timeout 600 --retries 5 -r requirements.txt

# Copy application
COPY src/services/model-management/main.py .
COPY src/services/model-management/config.py .
COPY src/services/model-management/models ./models
COPY src/services/model-management/core /app/core
COPY src/services/model-management/routes /app/routes

# Copy shared modules (shared.* imported via /app/src on sys.path). The plugin
# bootstrap config (src/bootstrap/) is intentionally NOT copied — only
# plugin-state-manager reads it, and it's mounted there from docker-compose.yml.
COPY src/shared /app/src/shared

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8005

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8005/health || exit 1

# Run application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8005"]
