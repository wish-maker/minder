FROM python:3.11-slim

WORKDIR /app

# Set Python environment
ENV PYTHONPATH=/app:$PYTHONPATH
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies for ML
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    g++ \
    cmake \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY services/model-management/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY services/model-management/main.py .

# Copy core modules
COPY src/core /app/src/core

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
