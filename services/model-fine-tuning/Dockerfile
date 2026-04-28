# Minder Model Fine-Tuning Service Dockerfile
# Simplified single-stage build for better compatibility

FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create directories for training data and models
RUN mkdir -p /app/training-data /app/models

# Copy requirements first for caching
COPY services/model-fine-tuning/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --timeout 600 --retries 5 -r requirements.txt || \
    pip install --no-cache-dir --timeout 600 --retries 5 -r requirements.txt

# Copy application code
COPY services/model-fine-tuning/main.py .

# Create non-root user for security
RUN useradd -m -u 1000 finetune && \
    chown -R finetune:finetune /app
USER finetune

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8007/health || exit 1

# Expose port
EXPOSE 8007

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8007"]
