# Manual Tests

Tests that need a **running Minder stack** (real services + databases) and are
run by hand, not in CI/CD. They make real connections rather than mocking, so
they're excluded from the automated pipelines.

## Available Tests

### test_database_writes.py
Verifies that plugins can write to their backing databases using real
connections (Postgres / Redis / Qdrant / Neo4j / InfluxDB).

### test_end_to_end.py
Exercises end-to-end flows against the running services with real data.

## How to Run

```bash
# Bring the stack up first (see repo root: bash setup.sh), then from project root:
python tests/manual/test_end_to_end.py
pytest tests/manual/test_database_writes.py -v
```

## Notes

- These are **excluded from CI/CD** (not in GitHub Actions, not required for PR
  approval) — they need live services and can be flaky depending on stack state.
- They may fail if a required service is down or still starting; that is
  expected. Bring the full stack up and retry.
