# src/services/marketplace/Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies. apt-get upgrade pulls in Debian security
# patches already available for base-image packages (e.g. util-linux's
# CVE fixes) that the pinned python:3.12-slim layer predates.
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set PYTHONPATH to include the parent directory
ENV PYTHONPATH=/app:$PYTHONPATH

# Copy requirements first for caching
COPY src/services/marketplace/requirements.txt .

# pip itself (bundled with python:3.12-slim) ships a version with known CVEs
# (e.g. CVE-2026-8643) that predate this Dockerfile -- bump before installing
# any requirements, as its own cacheable layer.
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir --timeout 600 --retries 5 -r requirements.txt || \
    pip install --no-cache-dir --timeout 600 --retries 5 -r requirements.txt

# Copy application code
COPY src/services/marketplace/ .

# Copy shared libraries
COPY src/shared /app/src/shared

# Create non-root user
RUN useradd -m -u 1000 marketplace && \
    chown -R marketplace:marketplace /app
USER marketplace

# Expose port
EXPOSE 8002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

# Run application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
