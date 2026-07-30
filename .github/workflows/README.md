# Minder CI/CD Pipeline

GitHub Actions workflows for this repository. Five workflows, each a single
concern. There is **no** build/push or deploy workflow — this is a self-hosted
Raspberry Pi platform provisioned via `setup.sh`, not a published image.

## Workflows

> Layout consolidated in #16: linters + light scans collapsed into one fast
> `quality.yml` gate, tests in `ci.yml`, deep scans in `security.yml`. bandit +
> safety previously ran in two workflows — now a single home in `quality.yml`.

### 1. Quality Gate — `quality.yml`
**Triggers:** push & PR to `main`/`develop`, manual dispatch.
**Jobs (all parallel — the fast gate):**
- Python lint: Black, isort, Flake8 (on `src/services/`, `src/shared/`, `scripts/`,
  `tests/`) + MyPy. MyPy is a **real gate** (#33): it runs per-service (each service
  dir is its own import root) with the pydantic plugin and installs
  `requirements-typecheck.txt` so FastAPI/Pydantic/httpx/etc. are checked with real
  types instead of `Any`. Config lives in the root `pyproject.toml` (`[tool.mypy]`),
  passed via `--config-file`. Also covers `src/shared/` and `scripts/setup/`.
- Shell lint: `bash -n` + `shellcheck --shell=bash --severity=error` (**blocking**)
  on `setup.sh` (the thin shim) + `setup.bash.sh` (the frozen bash reference) + all
  `scripts/lib/*.sh`; full-severity shellcheck is informational (`continue-on-error`).
  The file list is a glob, so new modules are covered automatically.
- Hadolint on `src/services/*/Dockerfile`.
- Light security scans: Bandit (`-r src/ src/services/ src/plugins/ tests/ -ll`),
  Safety, TruffleHog (secret scan), pip-licenses.

### 2. CI — `ci.yml`
**Triggers:** push & PR to `main`/`develop`, manual dispatch.
**Jobs:** unit tests → integration tests → e2e tests (pytest, with Postgres + Redis
service containers) → notify. Each stage `needs` the previous. Lint/scan gates live
in `quality.yml` (separate workflow, run in parallel).

### 3. Security Scan — `security.yml`
**Triggers:** push & PR to `main`/`develop`, weekly cron (Wed 09:00 UTC), manual
dispatch.
**Jobs:** the **deep** scans — CodeQL (Python SAST) + Trivy (builds `api-gateway`
from the compose file and scans the image for CVEs), plus a summary.
**Kept push-triggered (not scheduled-only):** on this repo CodeQL is ~1 min and
Trivy ~45 s, the repo is public (free CI minutes), and both run in parallel with
`ci.yml` off the critical path — so gating every push costs ~0 wall-clock while
closing the exposure window on an internet-exposed target. The weekly cron stays as
defense-in-depth. (#16 Option 2; the issue's written "scheduled-only" assumed heavy
scans, which the runtime data disproved.)

### 4. Docker Image Auto-Update — `docker-image-update.yml`
**Triggers:** weekly cron (Mon 09:00 UTC), manual dispatch.
**Behavior:** **issue-only** dependency engine. Reads
`docker/docker-compose.yml`, classifies third-party image updates as
safe/risky (local `minder/*` builds excluded), and opens (or updates) a single
tracking **issue** — it does not open PRs or modify files.

> The older auto-PR workflow (`auto-update-pr.yml`) that edited files and opened
> a PR was **retired** — it was superseded by the issue-only engine above (the
> PR approach edited compose without a rebuild, a "deploy illusion").

### 5. Dependency Update — `dependency-update.yml`
**Triggers:** weekly cron, manual dispatch.
**Behavior:** **issue-only** Python-dependency engine. Runs
`scripts/check_pip_updates.py` (stdlib `urllib`) to scan every `src/**/requirements*.txt`
against PyPI, classifies updates as major/minor/patch, and opens (or updates) a single
`[dependencies, python]` tracking **issue**. The Docker-image counterpart is `#4`.

## Local checks

```bash
# Shell (matches the Quality Gate workflow)
bash -n setup.sh setup.bash.sh scripts/lib/*.sh
shellcheck --shell=bash --severity=error setup.sh setup.bash.sh scripts/lib/*.sh

# Python (matches the Quality Gate + CI workflows)
pip install -r src/requirements/requirements-dev.txt -r src/requirements/requirements-typecheck.txt
black --check src/services/ src/shared/ scripts/ tests/
isort --check-only src/services/ src/shared/ scripts/ tests/
flake8 src/services/ src/shared/ scripts/ tests/ --max-line-length=120
# mypy is per-service (config in pyproject.toml, passed explicitly because we cd in)
for d in src/services/*/; do (cd "$d" && mypy . --config-file "$PWD/../../../pyproject.toml"); done
pytest tests/ -v --cov=src
```

## Notes

- Branch protection is permissive (solo dev): direct pushes to `main` are
  allowed; PRs are gated by the required status checks.
- Reports (coverage, security, licenses) are uploaded as workflow artifacts.
