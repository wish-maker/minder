# Minder TTS/STT Service Dockerfile
# Simplified single-stage build for better compatibility

FROM python:3.12-slim

WORKDIR /app

# Install system dependencies. apt-get upgrade pulls in Debian security
# patches already available for base-image packages (e.g. util-linux's CVE
# fixes) that the pinned python:3.12-slim layer predates.
# flac: SpeechRecognition's recognize_google() shells out to the `flac` CLI to
# transcode non-WAV/AIFF audio before uploading - without it every /stt call
# fails at runtime with "FLAC conversion utility not available" (#246).
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libsndfile1 \
    ffmpeg \
    espeak-ng \
    flac \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY src/services/tts-stt/requirements.txt .

# pip itself (bundled with python:3.12-slim) ships a version with known CVEs
# (e.g. CVE-2026-8643) that predate this Dockerfile -- bump before installing
# any requirements, as its own cacheable layer.
RUN pip install --no-cache-dir --upgrade pip

# Install Python dependencies
RUN pip install --no-cache-dir --timeout 600 --retries 5 -r requirements.txt || \
    pip install --no-cache-dir --timeout 600 --retries 5 -r requirements.txt

# Bundle Piper voices for OFFLINE TTS (#18) — downloaded at build so no runtime
# network is needed on the Pi. en_US-lessac-low (default English) + tr_TR-dfki-medium
# (the only Turkish voice Piper's own catalog currently offers, checked live via
# `python -m piper.download_voices` with no args) + hfc_female/hfc_male-medium (#588:
# an explicitly gender-labeled, same-dataset English pair for voice selection --
# ~130MB combined, a real but bounded/one-time size tradeoff against the Pi-
# friendliness goal above, not unbounded voice bloat).
# download_voices writes to the CWD, so switch there via WORKDIR (hadolint DL3003).
ENV TTS_VOICES_DIR=/app/voices
WORKDIR /app/voices
RUN python -m piper.download_voices \
    en_US-lessac-low tr_TR-dfki-medium en_US-hfc_female-medium en_US-hfc_male-medium
WORKDIR /app

# Copy application code
COPY src/services/tts-stt/main.py .
COPY src/services/tts-stt/config.py .
COPY src/services/tts-stt/models ./models
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
