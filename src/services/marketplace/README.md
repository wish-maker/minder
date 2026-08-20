# marketplace

The plugin/tool **catalog** with license tiers and a Neo4j **dependency graph**
(`:8002`, FastAPI, ~2.7k LOC). Browse/search plugins, resolve their dependencies
and conflicts, issue and validate license keys, and hold the AI-tool catalog that
plugin-state-manager gates execution against. Interactive docs at `/docs`.

## Run / check

```bash
bash setup.sh start marketplace     # needs the minder_marketplace Postgres DB + Neo4j

curl http://localhost:8002/health
curl http://localhost:8002/v1/marketplace/plugins            # catalog
curl http://localhost:8002/v1/marketplace/plugins/search?q=telegraf
curl http://localhost:8002/v1/graph/dependencies/<plugin_id> # dependency graph

python scripts/dev/dev.py mypy marketplace
DB_PASSWORD=x JWT_SECRET=<32ch> REDIS_PASSWORD=x NEO4J_AUTH=neo4j/x \
  python -m pytest tests/unit/test_marketplace_*.py
```

## Route groups (see `/docs` for schemas)

| Prefix | Purpose |
|--------|---------|
| `/v1/marketplace/plugins` | Catalog: list, `search`, `featured`, one plugin, its `tools` (`routes/marketplace.py`) |
| `/v1/marketplace/plugins/{id}` | Management: `install`, `uninstall`, `enable`, `disable`, `installations` (`routes/management.py`, same prefix as the catalog above, different route file) |
| `/v1/marketplace/installations` | `activate` an install, `me` (my installs) |
| `/v1/marketplace/licenses` | Issue / `validate` license keys (HMAC, tiered) |
| `/v1/marketplace/ai` | AI-tool catalog: `tools`, `sync` (pull module `AI_TOOLS` from the registry) |
| `/v1/marketplace/submissions` | Submission/review workflow (`routes/submissions.py`, #402): `mine`, `{id}/submit` (developer); the review queue + `{id}/claim,approve,reject,archive` (admin) |
| `/v1/graph` | Neo4j dependency graph: `dependencies`, `conflicts/{id}`, `recommendations` |

The catalog is populated two ways. **First-party module plugins** are auto-synced
by `sync`, which reads module `AI_TOOLS` from plugin-registry using
`SERVICE_SYNC_TOKEN` service-auth (#87) and creates them already `approved`
(`origin='first_party'`). **Developer submissions** (#402) instead go through a
review workflow: `POST /v1/marketplace/plugins` from a *user* JWT creates a
`draft` (`origin='submitted'`, `submitted_by=<sub>`), the developer `submit`s it,
an admin `claim`s → `approve`s/`reject`s (rejection requires notes; the developer
may edit and resubmit), and only an `approved` listing is publicly visible. Every
transition is validated by the state machine in `core/review.py` (409 on an
illegal move) and appended to the `marketplace_plugin_reviews` audit table. The
service sync will not overwrite an `origin='submitted'` row (409), so a
name-collision can't let auto-sync clobber a human submission.
(Phase 1 = this backend + state machine + admin review; the developer submission
UX in the client SPA and versioned re-submission are the deferred Phase 2/3 of #402.)

## Layout

```
marketplace/
├── main.py                    # thin app: include the 5 routers
├── routes/
│   ├── marketplace.py         # catalog: list/search/featured/get
│   ├── installations.py       # activate / me
│   ├── licensing.py           # license issue / validate
│   ├── ai_tools.py            # AI-tool catalog + sync
│   ├── graph_dependencies.py  # dependency graph queries
│   └── management.py          # admin/management ops
├── core/
│   ├── database.py            # Postgres access (minder_marketplace DB)
│   ├── neo4j_client.py        # dependency-graph client
│   ├── plugin_repository.py   # catalog persistence
│   ├── ai_tools_importer.py   # module AI_TOOLS → catalog rows
│   ├── licensing.py           # HMAC license-key gen/verify, tier ranking
│   ├── security.py            # service-sync auth
│   └── validation.py          # request validation helpers
├── migrations/                # DB schema migrations
├── models/                    # plugin + installation Pydantic models
└── config.py                  # Settings (own DATABASE/NEO4J/LICENSE_SECRET namespace)
```

## Configuration (`config.py`)

Marketplace's config is **deliberately divergent** from the shared base (#223):
its own `DB_NAME=minder_marketplace`, a separate `REDIS_DB=1`, and imports use the
fully-qualified `from services.marketplace.X` form to avoid the one-process
test-harness `sys.path` collision — don't "standardize" these away.

- `DB_HOST`/`DB_NAME` — the isolated `minder_marketplace` Postgres DB.
- `REDIS_DB=1` — a separate Redis index from the platform default.
- `LICENSE_SECRET` (optional) — HMAC secret for license keys; **falls back to the
  required auto-generated `JWT_SECRET`** when unset (no weak default). Set only to
  decouple license keys from `JWT_SECRET`.
- `NEO4J_URI` + `NEO4J_AUTH` (`user/password`, **required**, `field_validator`
  fail-fast) — the dependency graph (shares the Neo4j instance with graph-rag,
  different node labels).
- `PLUGIN_REGISTRY_URL`, `MAX_PLUGINS_PER_USER` (default 100 — enforced on
  `POST .../install`, 409 once a user's *currently-installed* count hits it;
  re-enabling an already-installed plugin doesn't count toward the cap),
  `MAX_UPLOAD_SIZE_MB`, `RATE_LIMIT_PER_MINUTE`.

## Error conventions

Platform-wide `{"detail": ...}` shape + 4xx-for-bad-input / sanitized-5xx. See
**[`docs/api/reference.md` → Error Handling](../../../docs/api/reference.md)**.

## Tests

`tests/unit/test_marketplace_*.py` — catalog CRUD/search, the licensing HMAC
round-trip + tier checks, the AI-tools importer, and dependency-graph queries
(Postgres + Neo4j faked, loaded by-path per the one-process conftest harness).
