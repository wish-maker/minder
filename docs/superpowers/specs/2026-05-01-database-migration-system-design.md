# Database Migration System Design

**Date:** 2026-05-01
**Priority:** CRITICAL - Blocks safe deployments
**Status:** Design Phase

## Problem Statement

Minder Platform currently has **no database migration system**. Each service creates tables with `CREATE TABLE IF NOT EXISTS`, which means:
- ❌ No version control for schema changes
- ❌ Cannot rollback schema changes
- ❌ Cannot track which migrations have run
- ❌ Cannot deploy schema changes safely
- ❌ Cannot reproduce database state across environments

## Proposed Solution: Alembic Migration System

### Architecture

```
minder/
├── infrastructure/
│   └── docker/
│       └── postgres-init.sql          # Initial DB setup (keep)
├── migrations/                         # NEW: Central migration directory
│   ├── alembic.ini                     # Alembic configuration
│   ├── env.py                          # Migration environment
│   ├── script.py.mako                  # Template
│   └── versions/                       # Migration files
│       ├── 001_initial_schema.py       # Initial state
│       ├── 002_add_plugin_states.py    # Example migration
│       └── README
└── services/
    └── {service}/
        └── migrations/                 # Service-specific migrations (optional)
```

### Components

#### 1. Central Migration System
- **Alembic** - Industry-standard Python migration tool
- **Single source of truth** - All schema changes in one place
- **Version tracking** - `alembic_version` table tracks applied migrations
- **Rollback support** - Downgrade scripts for each migration

#### 2. Migration Scripts
Each migration includes:
- `upgrade()` - Apply schema change
- `downgrade()` - Reverse schema change
- Transaction wrapping for atomicity

#### 3. Service Integration
- Services check migration version on startup
- Auto-run pending migrations (configurable)
- Health check includes migration status

### Data Flow

```
Deployment Trigger
    ↓
Pull latest code
    ↓
Run migrations: alembic upgrade head
    ↓
Verify migration success
    ↓
Start services
    ↓
Health check: Verify migration version
```

### Implementation Strategy

#### Phase 1: Initial Setup (Day 1)
1. Install Alembic: `pip install alembic`
2. Initialize: `alembic init migrations`
3. Configure `alembic.ini`:
   - Database URL from environment
   - Migration directory: `migrations/versions/`
   - Version table: `alembic_version`

#### Phase 2: Initial Schema (Day 1)
1. Create `001_initial_schema.py` - Snapshot current state
2. Include all existing tables:
   - `plugin_states` (plugin-state-manager)
   - `default_plugins` (plugin-state-manager)
   - `plugin_dependencies` (plugin-state-manager)
   - `user_subscriptions` (plugin-state-manager)
   - Marketplace tables
   - All other service tables

#### Phase 3: Service Integration (Day 2)
1. Add migration check to service startup:
   ```python
   async def check_migrations():
       # Verify migrations are up-to-date
       # Log warning if not
       # Optionally block startup
   ```

2. Add migration endpoint to health checks:
   ```python
   @app.get("/health")
   async def health():
       return {
           "migration_version": get_current_migration(),
           "pending_migrations": get_pending_count()
       }
   ```

#### Phase 4: Operational Procedures (Day 3)
1. **Create migration**: `alembic revision -m "description"`
2. **Apply migration**: `alembic upgrade head`
3. **Rollback migration**: `alembic downgrade -1`
4. **View history**: `alembic history`

### Error Handling

#### Migration Failures
- **Atomic transactions** - Partial changes rollback automatically
- **Backup before migration** - Automatic PostgreSQL dump
- **Manual intervention** - Migration pauses on error, manual fix required

#### Rollback Scenarios
- **Schema changes** - Downgrade script reverses DDL
- **Data changes** - Downgrade script restores data (if possible)
- **Point-in-time recovery** - Use PostgreSQL WAL + backups

### Testing Strategy

1. **Unit tests**: Test upgrade/downgrade logic
2. **Integration tests**: Test migrations in dev environment
3. **Staging validation**: Run migrations in staging before production
4. **Rollback tests**: Verify downgrade scripts work

### Success Criteria

✅ All schema changes tracked in version control
✅ Can rollback any schema change
✅ Can reproduce database state across environments
✅ Migration status visible in health checks
✅ Zero data loss during migrations

### Estimated Timeline

- **Phase 1**: 2 hours (setup)
- **Phase 2**: 4 hours (initial schema)
- **Phase 3**: 4 hours (service integration)
- **Phase 4**: 2 hours (procedures)
- **Testing**: 4 hours

**Total**: 16 hours (2 days)

### Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Migration fails in production | HIGH | Pre-migration backup, staging validation |
| Long-running migrations block deployment | MEDIUM | Zero-downtime migration patterns |
| Data corruption during rollback | HIGH | Test downgrade scripts extensively |
| Migration conflicts between services | MEDIUM | Single central migration system |

---

## Approval Required

Before implementing:
1. ✅ Confirm Alembic as migration tool (vs Flyway, Liquibase, custom)
2. ✅ Confirm central migration directory (vs distributed per-service)
3. ✅ Confirm auto-migration on startup (vs manual migration step)
4. ✅ Confirm rollback strategy requirements

**Next Steps:** Upon approval, proceed to implementation plan.
