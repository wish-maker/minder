# AI Setup Guide

## Overview

Minder runs LLM inference through Ollama. In the default (internal) mode the
platform runs its own Ollama container and auto-pulls the configured models during
setup — no manual intervention required. You can also point Minder at an external
Ollama instead.

> Ollama listens on port 11434 **internal to the Docker network only** — it is not
> exposed on the host. Reach it from another container, from inside the Ollama
> container (`docker exec`), or via services that proxy to it.

## Ollama modes: internal, external, failover

Ollama has three modes, recorded in root `./.env` and selected with the
`ollama-mode` verb:

- **Internal (default):** `OLLAMA_BASE_URL` is **empty**. The platform-managed
  `minder-ollama` container runs (it is gated behind the `internal-ollama` compose
  profile, which activates only when `OLLAMA_BASE_URL` is empty).
- **External / native host:** `OLLAMA_BASE_URL` is **set** to a URL. The internal
  container stays inactive, and services talk to your external Ollama instead
  (same host, native install, or a remote GPU box).
- **Failover:** an external **primary** with **automatic fallback to the internal
  container** when the primary is unreachable — and automatic return to the primary
  once it recovers. Best of both: the speed/model-fleet of a strong external box
  while you're using it, and the platform keeps serving (from its own Ollama) when
  that box is off. See [Failover mode](#failover-mode-external-primary--internal-fallback).

Switch modes with the `ollama-mode` verb:

```bash
# Platform-managed Ollama container (default)
bash setup.sh ollama-mode internal

# External Ollama — defaults to the host at http://host.docker.internal:11434
bash setup.sh ollama-mode external

# External Ollama at a specific URL
bash setup.sh ollama-mode external http://192.168.1.50:11434

# Failover: external primary + automatic fallback to the internal container
bash setup.sh ollama-mode failover http://192.168.1.50:11434
```

This edits `./.env` (`OLLAMA_BASE_URL`, plus `OLLAMA_FAILOVER_PRIMARY` for failover);
it does **not** restart — run `bash setup.sh restart` to apply. In external mode the
local Ollama container is not started (it's gated behind the compose profile), saving
RAM/CPU; failover mode keeps it running as the warm standby.

### The URL must be reachable *from inside the containers*

`OLLAMA_BASE_URL` is resolved by the service containers on the Docker network — **not**
by your host shell. An address that works from the host (or only on your LAN's DNS) can
still be unreachable from a container. In particular:

- **Ollama running natively on the same machine as Docker:** use
  `http://host.docker.internal:11434` (Docker Desktop's host alias) or the host's LAN IP
  (`http://192.168.68.109:11434`). `http://localhost:11434` will **not** work from a
  container (localhost there is the container itself).
- **A bare hostname** (e.g. `http://gpu-node:11434`) only works if that name resolves
  *inside the containers*. If it resolves nowhere, inference silently breaks.

⚠️ **Failure mode (see [#77]):** if the URL is unreachable, document upload still returns
`200` but stores a **zero-vector** (the doc is never retrievable), and queries return
`"Error generating response: ... Name or service not known"`. Always verify from a
container, not the host:

```bash
# expect 200 — this is what the RAG/model-management services actually see
docker exec minder-rag-pipeline curl -s -o /dev/null -w '%{http_code}\n' \
  --max-time 5 "$OLLAMA_BASE_URL/api/tags"
```

Ollama must also be listening on all interfaces for containers to reach it — start the
native server with `OLLAMA_HOST=0.0.0.0` (not the default `127.0.0.1`).

## Single-host setup (Ollama already running natively)

**This applies if:** you already run Ollama on the same machine you're installing
Minder on — for other things, outside Minder — and want Minder to use that same
instance instead of running a second, separate one.

**The one required step:** point Minder at your existing Ollama with **external
mode**, set *before* (or right after) `install`:

```bash
# Either before installing, in ./.env:
OLLAMA_BASE_URL=http://host.docker.internal:11434   # see the address gotchas above for your OS

# Or right after installing:
bash setup.sh ollama-mode external http://host.docker.internal:11434
bash setup.sh restart
```

**Why not just leave it on internal mode too?** Internal mode starts a *second*,
platform-managed Ollama container alongside your native one — two separate Ollama
processes competing for the same GPU/RAM for no benefit, since external mode already
gives every Minder service (RAG pipeline, model management, gateway, OpenWebUI) the
exact same access to your native instance. External mode keeps the internal
container inactive (gated behind the `internal-ollama` compose profile), so this is
"free" — no extra config beyond the one URL above.

**Getting the URL right:** see [The URL must be reachable from inside the
containers](#the-url-must-be-reachable-from-inside-the-containers) above —
`host.docker.internal` (Docker Desktop on Windows/Mac), the host's LAN IP (Linux, or
if `host.docker.internal` isn't set up), never `localhost`.

**Do you need failover mode instead of plain external?** Only if you want Minder to
keep working when you manually stop your native Ollama for some other reason (e.g.
freeing the GPU for something else) — failover falls back to an internal container
that's otherwise sitting idle. For a single always-on host where your native Ollama
just runs continuously, plain external mode is simpler and this is unnecessary
complexity.

## Failover mode (external primary + internal fallback)

Failover mode gives you a fast external Ollama **without** the single point of failure
of plain external mode: if the external host goes away, the platform automatically
serves from its own internal container, and returns to the external host once it's back.

```bash
bash setup.sh ollama-mode failover http://192.168.1.50:11434
bash setup.sh restart
```

**How it works.** A small `minder-ollama-router` (nginx) sits in front of Ollama with
the external host as the **primary** and the internal `minder-ollama` container as the
**backup**. All services point at the router (`OLLAMA_BASE_URL=http://minder-ollama-router:11434`),
so failover is transparent — OpenWebUI included, no per-service change. When the primary
stops answering, requests (including generations) fail over to the internal container;
after a short interval the router re-probes the primary and returns to it automatically.
The internal container stays running as a warm standby (idle Ollama loads no model into
RAM, so it costs almost nothing until it actually serves a fallback request).

**See which backend is active:**

```bash
bash setup.sh status        # → "Ollama Backend" section: primary REACHABLE (external) / UNREACHABLE (fallback)

# Or per-response — the router reports the backend that served it:
docker exec minder-rag-pipeline curl -sI http://minder-ollama-router:11434/api/tags | grep -i x-ollama-upstream
```

> **Model availability on fallback.** Fallback is seamless only for models the internal
> container actually has — by default `llama3.2` + `nomic-embed-text` (see
> [Automatic model downloads](#automatic-model-downloads)). A knowledge base or query
> pinned to a model that lives **only** on the external primary (e.g. a large model the
> Pi can't run) will fail while the primary is unreachable. Keep your default/embedding
> models available on both sides.

## Automatic model downloads

**When:** On startup, in internal mode
**What:** Pulls the models listed in `OLLAMA_MODELS` (default llama3.2 + nomic-embed-text)
**Detection:** Skips a model if it already exists in the Ollama volume

Model storage lives in `/root/.ollama/models` inside the container, backed by a
Docker volume so models survive container recreation.

### Configuration

**Environment variables** (in root `./.env`):

```bash
# Models to auto-pull on startup (comma-separated)
OLLAMA_MODELS=llama3.2,nomic-embed-text

# Which models the services use for each purpose
OLLAMA_LLM_MODEL=llama3.2
OLLAMA_EMBEDDING_MODEL=nomic-embed-text

# Empty = internal container mode; set to a URL = external mode
OLLAMA_BASE_URL=
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

### Text Generation (Ollama, internal-only)

Ollama is not host-exposed, so call it from inside the container (or from another
container on `minder-network`):

```bash
# Generate text with llama3.2 from inside the container
docker exec minder-ollama curl -s -X POST http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2","prompt":"What is the capital of France?","stream":false}'

# Response: {"model":"llama3.2","response":"The capital of France is Paris.","done":true}
```

### RAG queries

The RAG Pipeline service (host-exposed on 8004) uses `OLLAMA_EMBEDDING_MODEL` for
vector embeddings and `OLLAMA_LLM_MODEL` for generation. See the
[RAG Methods Guide](../rag-methods.md) for the API.

### OpenWebUI

OpenWebUI is the web chat frontend. Its container port (8080) is not host-exposed;
it is reached through the Traefik reverse proxy. It auto-detects installed Ollama
models — pick one from the dropdown and start chatting.

## Customization

### Change Auto-Download Models

Edit root `./.env`:

```bash
# Pull different models on startup
OLLAMA_MODELS=mistral,qwen2.5,nomic-embed-text

# To disable automatic pulls, leave the list empty
OLLAMA_MODELS=
```

Then restart to apply:
```bash
bash setup.sh restart
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

### RAG Pipeline (:8004)

Uses `OLLAMA_EMBEDDING_MODEL` for vector embeddings and `OLLAMA_LLM_MODEL` for
generation. See the [RAG Methods Guide](../rag-methods.md) for the knowledge-base
and query endpoints.

### Model Management (:8005)

Lists, pulls, deletes, and tests Ollama models via the Ollama API. Note that
`/models/{id}/constraints` and `/models/{id}/metrics` are placeholders.

### OpenWebUI

Web chat frontend (reached via Traefik) with:
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

- 📖 Read [RAG Methods Guide](../rag-methods.md)
- 🚀 Deploy to [Production](../deployment/production.md)

---

**Last Updated:** 2026-07-10
