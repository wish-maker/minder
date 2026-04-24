# Crypto Plugin Dockerfile
# Multi-stage build for optimal image size
FROM python:3.13-slim as builder

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies
COPY src/plugins/crypto/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Runtime stage
FROM python:3.13-slim

# Create non-root user for security
RUN useradd -m -u 1000 plugin && \
    mkdir -p /app && \
    chown -R plugin:plugin /app

WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages

# Copy plugin code
COPY src/plugins/crypto/plugin.py .
COPY src/plugins/crypto/main.py .
COPY src/plugins/crypto/database.py .
COPY src/plugins/crypto/utils/ ./utils/
COPY src/plugins/crypto/manifest.yml .

# Switch to non-root user
USER plugin

# Expose port
EXPOSE 8002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8002/health')" || exit 1

# Run application
CMD ["python", "main.py"]
