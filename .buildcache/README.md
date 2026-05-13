# Minder Platform - BuildKit Cache Directory

This directory stores Docker BuildKit cache for faster rebuilds.

## Structure
- `layers/` - Cached layer data
- `metadata/` - Build metadata and checksums
- `tmp/` - Temporary build files

## Cache Invalidation
Cache is invalidated based on:
1. Dockerfile changes
2. Source code modifications (checksums)
3. Build context changes
4. Environment variable changes

## Cleanup
To clean cache and reclaim space:
```bash
docker builder prune
```

## Performance
Expected improvements:
- First build: ~5-10 minutes (baseline)
- Cached build: ~30-60 seconds (90% faster)
- Incremental changes: ~10-30 seconds
