FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Set PYTHONPATH
ENV PYTHONPATH=/app:$PYTHONPATH

# Install system dependencies. apt-get upgrade pulls in Debian security
# patches already available for base-image packages (e.g. util-linux's CVE
# fixes) that the pinned python:3.12-slim layer predates.
# nmap: host/port/service discovery for the network plugin (connect scan -sT, no
#       root needed). snmp: net-snmp CLI (snmpget) for SNMP OID lookup.
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    python3-dev \
    nmap \
    snmp \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY src/services/plugin-registry/requirements.txt .

# pip itself (bundled with python:3.12-slim) ships a version with known CVEs
# (e.g. CVE-2026-8643) that predate this Dockerfile -- bump before installing
# any requirements, as its own cacheable layer.
RUN pip install --no-cache-dir --upgrade pip

# Install Python dependencies
RUN pip install --no-cache-dir --timeout 600 --retries 5 -r requirements.txt || \
    pip install --no-cache-dir --timeout 600 --retries 5 -r requirements.txt

# Plugin-specific deps (tefas-crawler) are pinned in requirements.txt above — no
# separate install step. borsapy was removed (#750): a dead pin nothing imported,
# and its AGPL pymupdf transitive was a licensing risk. influxdb-client was
# removed (#341): never imported (plugins write to InfluxDB via raw httpx
# line-protocol calls instead).

# Copy application code
COPY src/services/plugin-registry/main.py .
COPY src/services/plugin-registry/config.py .
COPY src/services/plugin-registry/models ./models
COPY src/services/plugin-registry/schema.sql .
COPY src/services/plugin-registry/routes /app/routes
COPY src/services/plugin-registry/core /app/core
COPY src/services/plugin-registry/schemas /app/schemas

# Copy shared core library and plugins (from build context)
COPY src/shared /app/src/shared
COPY src/plugins /app/plugins

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8001/health || exit 1

# Run application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
