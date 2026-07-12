FROM python:3.12-slim

WORKDIR /app

# Set Python environment
ENV PYTHONPATH=/app:$PYTHONPATH
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY src/services/rag-pipeline/requirements.txt .
RUN pip install --no-cache-dir --timeout 600 --retries 5 -r requirements.txt || \
    pip install --no-cache-dir --timeout 600 --retries 5 -r requirements.txt

# Copy application
COPY src/services/rag-pipeline/main.py .
COPY src/services/rag-pipeline/config.py .
COPY src/services/rag-pipeline/models.py .
COPY src/services/rag-pipeline/pg_client.py .
COPY src/services/rag-pipeline/config.yaml .
COPY src/services/rag-pipeline/quality_evaluator.py .
COPY src/services/rag-pipeline/repositories /app/repositories

# Advanced RAG method modules (HyDE, Self-RAG, decision engine) — wired into the
# query endpoint via the `method` field (see #45).
COPY src/services/rag-pipeline/domain /app/domain
COPY src/services/rag-pipeline/agent /app/agent
# Query orchestration (per-method strategies + runner)
COPY src/services/rag-pipeline/rag /app/rag

# Copy core modules
COPY src/core /app/src/core

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8004

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8004/health || exit 1

# Run application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8004"]
