# Minder TTS/STT Service Dockerfile
# Simplified single-stage build for better compatibility

FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libsndfile1 \
    ffmpeg \
    espeak-ng \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY src/services/tts-stt/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --timeout 600 --retries 5 -r requirements.txt || \
    pip install --no-cache-dir --timeout 600 --retries 5 -r requirements.txt

# Bundle Piper voices for OFFLINE TTS (#18) — downloaded at build so no runtime
# network is needed on the Pi. en_US-lessac-low + tr_TR-dfki-medium (Turkish).
ENV TTS_VOICES_DIR=/app/voices
RUN mkdir -p /app/voices && cd /app/voices && \
    python -m piper.download_voices en_US-lessac-low tr_TR-dfki-medium

# Copy application code
COPY src/services/tts-stt/main.py .
COPY src/services/tts-stt/config.py .
COPY src/services/tts-stt/models.py .
COPY src/services/tts-stt/core /app/core
COPY src/services/tts-stt/routes /app/routes

# Shared library (shared.* imported via /app/src on sys.path)
COPY src/shared /app/src/shared

# Create non-root user for security
RUN useradd -m -u 1000 ttsst && \
    chown -R ttsst:ttsst /app
USER ttsst

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8006/health || exit 1

# Expose port
EXPOSE 8006

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8006"]
