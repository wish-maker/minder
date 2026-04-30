# Automatic AI Setup Guide

## Overview

Minder Platform features zero-configuration AI setup with automatic model downloads. No manual intervention required - the platform downloads and configures AI models during the initial setup.

## How It Works

### Automatic Model Downloads

**When:** During `./setup.sh` execution  
**What:** Downloads llama3.2 (2GB) + nomic-embed-text (274MB)  
**Time:** ~3 minutes (depends on internet speed)  
**Detection:** Skips download if models already exist

### Configuration

**Environment Variables** (in `infrastructure/docker/.env`):

```bash
# Enable automatic model download (default: true)
OLLAMA_AUTOMATIC_PULL=true

# Models to download (comma-separated)
OLLAMA_MODELS=llama3.2,nomic-embed-text

# Specific models for different purposes
OLLAMA_LLM_MODEL=llama3.2
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
```

## Available Models

### LLM Models

**llama3.2** (2.0GB) - General purpose LLM
- Great for text generation, chatbots, content creation
- Fast inference with good quality
- Recommended for most use cases

**mistral** (4.1GB) - High performance LLM
- Better for complex reasoning
- Slower but higher quality
- Requires more RAM

**qwen2.5** (2.5GB) - Multilingual LLM
- Excellent for non-English text
- Good translation capabilities
- Moderate resource usage

### Embedding Models

**nomic-embed-text** (274MB) - Text embeddings
- Fast and efficient
- Great for RAG pipelines
- Recommended default

**mxbai-embed-large** (669MB) - Large embeddings
- Higher quality embeddings
- Better for complex semantic search
- Slower but more accurate

## Usage Examples

### Text Generation

```bash
# Generate text with llama3.2
curl -X POST http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2","prompt":"What is the capital of France?","stream":false}'

# Response: {"model":"llama3.2","response":"The capital of France is Paris.","done":true}
```

### Embeddings for RAG

```bash
# Generate embeddings with nomic-embed-text
curl -X POST http://localhost:8004/api/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello, this is a test"}'

# Response: {"embedding":[0.1,0.2,...],"dimension":768}
```

### OpenWebUI Integration

```bash
# Access web interface at http://localhost:8080
# Automatically detects all installed models
# Select model from dropdown and start chatting
```

## Customization

### Change Auto-Download Models

Edit `infrastructure/docker/.env`:

```bash
# Download different models
OLLAMA_MODELS=mistral,qwen2.5,nomic-embed-text

# Disable automatic downloads
OLLAMA_AUTOMATIC_PULL=false
```

Then restart:
```bash
docker compose -f infrastructure/docker/docker-compose.yml restart ollama
```

### Manual Model Management

```bash
# Check installed models
docker exec minder-ollama ollama list

# Download additional models
docker exec minder-ollama ollama pull mistral

# Remove models to free space
docker exec minder-ollama ollama rm mistral

# Show model info
docker exec minder-ollama ollama show llama3.2
```

## Integration with Services

### RAG Pipeline

Uses `OLLAMA_EMBEDDING_MODEL` for vector embeddings:

```bash
curl -X POST http://localhost:8004/api/v1/rag/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the capital of France?",
    "collection": "knowledge-base"
  }'
```

### Model Management

Tracks registered models:

```bash
curl http://localhost:8005/api/v1/models/list
```

### OpenWebUI

Web interface at http://localhost:8080 with:
- Model selection dropdown
- Chat interface
- RAG integration
- Tool calling support

## Troubleshooting

### Models Not Downloading

**Check if automatic pull is enabled:**
```bash
docker logs minder-ollama | grep -i "automatic"
```

**Manually trigger download:**
```bash
docker exec minder-ollama ollama pull llama3.2
```

### Download Failed

**Check Ollama logs:**
```bash
docker logs minder-ollama
```

**Common causes:**
- Insufficient disk space
- Network connectivity issues
- Corrupted download (retry)

**Solution:**
```bash
# Remove corrupted model
docker exec minder-ollama ollama rm llama3.2

# Re-download
docker exec minder-ollama ollama pull llama3.2
```

### Out of Space

**Check disk usage:**
```bash
docker exec minder-ollama du -sh /root/.ollama
```

**Remove unused models:**
```bash
docker exec minder-ollama ollama list
docker exec minder-ollama ollama rm <model-name>
```

## Performance Tips

### RAM Requirements

- **llama3.2**: 4GB RAM minimum
- **mistral**: 8GB RAM recommended
- **qwen2.5**: 6GB RAM recommended
- **nomic-embed-text**: 1GB RAM sufficient

### CPU Requirements

- **Minimum**: 4 cores for acceptable performance
- **Recommended**: 8 cores for smooth operation
- **Optimal**: 16+ cores for production workloads

### Disk Space

- **Base models**: 3GB (llama3.2 + nomic-embed-text)
- **Additional models**: 2-8GB each
- **Recommended free space**: 20GB minimum

## Production Considerations

### Model Selection

**Development:** Use llama3.2 (fast, good quality)
**Production:** Consider mistral (better quality)
**Multilingual:** Use qwen2.5 (best translation)
**RAG:** nomic-embed-text (fast, efficient)

### Scaling

**Horizontal scaling:** Multiple Ollama instances with load balancing
**Vertical scaling:** Increase RAM/CPU for better inference speed
**Model caching:** Pre-load models in memory for faster responses

### Monitoring

**Track model usage:**
```bash
docker exec minder-ollama ollama ps
```

**Monitor resource usage:**
```bash
docker stats minder-ollama
```

## Next Steps

- 📖 Read [RAG Pipeline Guide](../guides/rag-pipeline.md)
- 🔧 Configure [Model Fine-tuning](../development/model-fine-tuning.md)
- 🚀 Deploy to [Production](../deployment/production.md)
