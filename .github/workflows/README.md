# Minder CI/CD Pipeline

GitHub Actions workflows for this repository. Four workflows, each a single
concern. There is **no** build/push or deploy workflow — this is a self-hosted
Raspberry Pi platform provisioned via `setup.sh`, not a published image.

## Workflows

### 1. Test Suite — `test.yml`
**Triggers:** push & PR to `main`/`develop`, manual dispatch.
**Jobs:** Python lint (Black, isort, Flake8, MyPy on `src/`) → security scan
(Bandit, Safety) → unit tests → integration tests → e2e tests (pytest, with
Postgres + Redis service containers) → notify. Later test stages depend on the
earlier ones passing.

### 2. Security Scan — `security.yml`
**Triggers:** push & PR to `main`/`develop`, weekly cron (Wed 09:00 UTC), manual
dispatch.
**Jobs:** CodeQL (Python), Bandit, Safety, Trivy (builds `api-gateway` from the
compose file and scans the image), TruffleHog (secret scan), Hadolint
(`src/services/*/Dockerfile`), pip-licenses, and a summary.

### 3. Shell Lint — `shell-lint.yml`
**Triggers:** push & PR to `main`/`develop`, manual dispatch.
**Jobs:** lints `setup.sh` + all `scripts/lib/*.sh` modules.
- `bash -n` (syntax) — **blocking**.
- `shellcheck --shell=bash --severity=error` — **blocking** (`--shell=bash` is
  required because the modules are sourced and carry no shebang).
- `shellcheck` at full severity — **informational** (`continue-on-error`),
  surfaces style/warning nits without failing the build.

The file list is a glob, so newly added modules are covered automatically.

### 4. Docker Image Auto-Update — `docker-image-update.yml`
**Triggers:** weekly cron (Mon 09:00 UTC), manual dispatch.
**Behavior:** **issue-only** dependency engine. Reads
`docker/compose/docker-compose.yml`, classifies third-party image updates as
safe/risky (local `minder/*` builds excluded), and opens (or updates) a single
tracking **issue** — it does not open PRs or modify files.

> The older auto-PR workflow (`auto-update-pr.yml`) that edited files and opened
> a PR was **retired** — it was superseded by the issue-only engine above (the
> PR approach edited compose without a rebuild, a "deploy illusion").

## Local checks

```bash
# Shell (matches the Shell Lint workflow)
bash -n setup.sh scripts/lib/*.sh
shellcheck --shell=bash --severity=error setup.sh scripts/lib/*.sh

# Python (matches the Test Suite workflow)
black --check src/services/ src/core/
flake8 src/services/ src/core/ --max-line-length=120
pytest tests/ -v --cov=src
```

## Notes

- Branch protection is permissive (solo dev): direct pushes to `main` are
  allowed; PRs are gated by the required status checks.
- Reports (coverage, security, licenses) are uploaded as workflow artifacts.
