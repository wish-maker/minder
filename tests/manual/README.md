# Manual Tests

Tests that need a **running Minder stack** (real services + databases) and are
run by hand, not in CI/CD. They make real connections rather than mocking, so
they're excluded from the automated pipelines.

## Available Tests

### test_real_user_journeys.py
Real user journeys against a live, running stack: register/login, plain chat
(real Ollama inference, not a stub), tool-calling chat against the real
crypto/weather/news plugins, a full RAG document lifecycle (create KB ->
upload -> pipeline -> query -> cleanup) against real Qdrant, and the
unauthenticated-mutating-action security boundary. Complements
`tests/e2e/`, which proves the dispatch *code* is correct with a scripted,
deterministic model — this proves the *deployed* system, with whatever model
is actually installed, gives a sane answer to a real question. Run it after
every `setup.sh update` against a live box (hantal/pi), not as a CI gate.

Supersedes `test_end_to_end.py` / `test_database_writes.py` (removed): both
had rotted into calling routes that no longer exist and importing a
monolithic `src.core.kernel.MinderKernel` removed when the codebase became
microservices — unconditionally skipped, so nobody noticed.

## How to Run

```bash
# Bring the stack up first (see repo root: bash setup.sh), then from project root:
python tests/manual/test_real_user_journeys.py --base-url http://localhost:8000
```

## Notes

- These are **excluded from CI/CD** (not in GitHub Actions, not required for PR
  approval) — they need live services and can be flaky depending on stack state.
- They may fail if a required service is down or still starting; that is
  expected. Bring the full stack up and retry.
