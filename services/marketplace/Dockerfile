# services/marketplace/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set PYTHONPATH to include the parent directory
ENV PYTHONPATH=/app:$PYTHONPATH

# Copy requirements first for caching
COPY services/marketplace/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY services/marketplace/ .

# Copy the services package structure
COPY services/ ./services/

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
