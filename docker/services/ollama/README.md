# Ollama Automatic Model Setup

This directory contains the automatic model download system for Ollama.

## How It Works

1. **init-models.sh**: This script runs automatically when the Ollama container starts for the first time
2. **Environment Variables**: Control which models are downloaded
3. **Smart Detection**: Checks if models already exist to avoid re-downloading

## Configuration

### Environment Variables

Set these in `infrastructure/docker/.env`:

```bash
# Enable automatic model download (default: true)
OLLAMA_AUTOMATIC_PULL=true

# Models to download (comma-separated)
OLLAMA_MODELS=llama3.2,nomic-embed-text,mistral,qwen2.5

# Specific models for different purposes
OLLAMA_LLM_MODEL=llama3.2
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
```

### Available Models

**LLM Models:**
- `llama3.2` (2.0GB) - General purpose LLM
- `mistral` (4.1GB) - High performance LLM
- `qwen2.5` (2.5GB) - Multilingual LLM

**Embedding Models:**
- `nomic-embed-text` (274MB) - Text embeddings
- `mxbai-embed-large` (669MB) - Large embeddings

## Manual Model Management

### Check Installed Models

```bash
docker exec minder-ollama ollama list
```

### Download Additional Models

```bash
docker exec minder-ollama ollama pull mistral
```

### Remove Models

```bash
docker exec minder-ollama ollama rm mistral
```

### Test Model

```bash
curl -X POST http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2","prompt":"Hello!","stream":false}'
```

## Troubleshooting

### Models Not Downloading

Check if automatic pull is enabled:

```bash
docker logs minder-ollama | grep -i "automatic"
```

### Download Failed

Manually trigger download:

```bash
docker exec minder-ollama ollama pull llama3.2
```

### Out of Space

Check disk usage:

```bash
docker exec minder-ollama du -sh /root/.ollama
```

Remove unused models:

```bash
docker exec minder-ollama ollama list
docker exec minder-ollama ollama rm <model-name>
```

## Integration with Minder Services

### RAG Pipeline

Uses `OLLAMA_EMBEDDING_MODEL` for vector embeddings:

```bash
curl -X POST http://localhost:8004/api/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello world"}'
```

### OpenWebUI

Automatically detects available models:

```bash
curl http://localhost:8080/api/models
```

### Model Management

Tracks registered models:

```bash
curl http://localhost:8005/api/v1/models/list
```
