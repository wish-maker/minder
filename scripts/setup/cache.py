"""Tag cache — ported from scripts/lib/cache.sh (#7, Stage 2).

On-disk cache of registry tag lists (`.cache/<registry>/<repo>.json`) with a
24h TTL, used by the version-resolution engine. Ported ahead of its consumer
(`versions`, still bash) as the next foundation module in dependency order —
`versions` calls these directly, so it lands next.

Faithful to cache.sh: `cache_file` maps `/` → `--` in the repo name; expiry is
mtime-vs-TTL (missing file = expired); `load_cached_tags` reproduces the
tr/grep/sed parse of the `"tags": [...]` block; `cache_tags` writes the same
JSON shape and emits the trailing `log_debug "Cached tags to …"` (VERBOSE-gated,
LOG_FILE-mirrored) now that the log module ports file-mirroring.
"""

import re
import time
from pathlib import Path

from . import config, log


def cache_file(registry: str, repo: str) -> Path:
    """bash _cache_file: ${CACHE_DIR}/${registry}/${repo//\\//--}.json (/ → --)."""
    safe_repo = repo.replace("/", "--")
    return config.CACHE_DIR / registry / f"{safe_repo}.json"


def cache_expired(path: Path) -> bool:
    """bash _cache_expired: True if the file is missing or older than the TTL.

    Mirrors `[[ ! -f ]] && return 0` (missing = expired) then age-vs-TTL using
    integer seconds like `date +%s` / `stat -c %Y`.
    """
    if not path.is_file():
        return True
    try:
        cache_time = int(path.stat().st_mtime)
    except OSError:
        cache_time = 0
    cache_age = int(time.time()) - cache_time
    return cache_age > config.CACHE_TTL_HOURS * 3600


def load_cached_tags(path: Path) -> str:
    """bash _load_cached_tags: the cached tags (one per line) or "" when expired /
    missing / unparseable. Reproduces the flatten → extract `"tags":[...]` →
    strip brackets/quotes → split on commas → trim → drop-empty pipeline.
    """
    if cache_expired(path):
        return ""
    if not path.is_file():
        return ""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    # tr '\n' ' '  then  grep -oE '"tags"\s*:\s*\[[^]]*\]'
    flat = content.replace("\n", " ")
    match = re.search(r'"tags"[ \t]*:[ \t]*\[[^\]]*\]', flat)
    if not match:
        return ""
    block = match.group(0)
    # sed 's/.*\[//; s/\].*//'  → the content between the first [ and the next ]
    inner = block[block.index("[") + 1 : block.index("]")]
    # s/"//g ; s/,/\n/g  → drop quotes, commas become line breaks
    inner = inner.replace('"', "").replace(",", "\n")
    # per line: trim leading/trailing whitespace; then drop empty lines
    tags = [ln.strip() for ln in inner.split("\n")]
    return "\n".join(t for t in tags if t)


def cache_tags(path: Path, tags: str, timestamp: str) -> None:
    """bash _cache_tags: write the tag list as JSON with a UTC timestamp.

    The timestamp is passed in (rather than sampled here) so the writer stays
    deterministic/testable; callers pass `date -u +%Y-%m-%dT%H:%M:%SZ`.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # echo "$tags" | sed 's/^/    "/;s/$/",/' | sed '$ s/,$//'
    lines = [f'    "{ln}",' for ln in tags.split("\n")]
    if lines:
        lines[-1] = lines[-1][:-1]  # $ s/,$// — strip the last line's trailing comma
    body = "\n".join(lines)
    content = f'{{\n  "timestamp": "{timestamp}",\n  "tags": [\n{body}\n  ]\n}}\n'
    # newline="" so we never translate \n -> \r\n (bash writes LF; keep the cache
    # file byte-identical + cross-OS stable, same reason ollama.py opens .env raw).
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(content)
    log.debug(f"Cached tags to {path}")  # VERBOSE-gated, LOG_FILE only
