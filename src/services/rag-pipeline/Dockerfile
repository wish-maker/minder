FROM python:3.12-slim

WORKDIR /app

# Set Python environment. /app/src is on the path so `shared.*` resolves the moment
# any module imports it — including route modules (routes.system → shared.health)
# that load BEFORE main.py's own sys.path.insert runs. Without /app/src here a fresh
# build crash-loops with "ModuleNotFoundError: No module named 'shared'".
ENV PYTHONPATH=/app/src:/app:$PYTHONPATH
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

# pip itself (bundled with python:3.12-slim) ships a version with known CVEs
# (e.g. CVE-2026-8643) that predate this Dockerfile -- bump before installing
# any requirements, as its own cacheable layer.
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir --timeout 600 --retries 5 -r requirements.txt || \
    pip install --no-cache-dir --timeout 600 --retries 5 -r requirements.txt

# Copy application
COPY src/services/rag-pipeline/main.py .
COPY src/services/rag-pipeline/config.py .
COPY src/services/rag-pipeline/models ./models
COPY src/services/rag-pipeline/schema.sql .
COPY src/services/rag-pipeline/routes /app/routes
# App-level state + wiring lives in core/ (was a root state.py).
COPY src/services/rag-pipeline/core /app/core
# pg_client.py now lives in repositories/ (persistence) and quality_evaluator.py in
# domain/ — both copied with their packages below, no standalone COPY needed.
COPY src/services/rag-pipeline/repositories /app/repositories

# Advanced RAG method modules (HyDE, Self-RAG, decision engine) — wired into the
# query endpoint via the `method` field (see #45). The decision engine now lives in
# domain/decision_engine.py (was a standalone agent/ package).
COPY src/services/rag-pipeline/domain /app/domain
# Query orchestration (per-method strategies + runner)
COPY src/services/rag-pipeline/rag /app/rag

# Copy core + shared modules (shared.* imported via /app/src on sys.path)
COPY src/shared /app/src/shared

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
