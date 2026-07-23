FROM python:3.12-slim

WORKDIR /app

# Set Python environment
ENV PYTHONPATH=/app:$PYTHONPATH
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies for ML
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    g++ \
    cmake \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY src/services/model-management/requirements.txt .
RUN pip install --no-cache-dir --timeout 600 --retries 5 -r requirements.txt || \
    pip install --no-cache-dir --timeout 600 --retries 5 -r requirements.txt

# Copy application
COPY src/services/model-management/main.py .
COPY src/services/model-management/config.py .
COPY src/services/model-management/models.py .
COPY src/services/model-management/core /app/core
COPY src/services/model-management/routes /app/routes

# Copy shared modules (shared.* imported via /app/src on sys.path). The framework
# src/core is intentionally NOT copied — this service doesn't import it, and doing so
# would shadow the service-local core/ package on sys.path (mirrors graph-rag).
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
