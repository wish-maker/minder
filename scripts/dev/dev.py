"""Dev-loop helpers: collapse the repetitive CI-poll / lint / mypy / test command
sequences this project's PR flow repeats into one call each — fewer, cheaper shell
round-trips.

Not part of the platform runtime, the setup CLI (`scripts/setup/`), or the parity
gate (`scripts/gate/`) — a developer convenience, sibling to `pi_ssh.py`.

    python scripts/dev/dev.py ci <PR> [--watch]   # CI verdict; --watch polls to terminal
    python scripts/dev/dev.py lint <path>...       # black --check + isort + flake8 (CI flags)
    python scripts/dev/dev.py mypy <service>       # per-service mypy with the repo config
    python scripts/dev/dev.py test [pytest args]   # unit tests (tests/unit by default)

`ci --watch` is the big win: it polls `gh pr checks` until every check reaches a
terminal state and prints a one-line verdict, replacing a hand-run sleep+grep loop.
It's safe to run in the background — you get the verdict when CI finishes.

The lint/flake8 flags mirror `.github/workflows/quality.yml` exactly, and `mypy` uses
the repo `pyproject.toml` config with each service dir as its own import root (the
per-service layout the CI gate uses) — so a green local run predicts a green CI run.
"""

import argparse
import io
import subprocess
import sys
import time

# UTF-8 stdout so ✓/✗ glyphs don't crash a cp1254 Windows console (mirrors pi_ssh.py).
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

FLAKE8_FLAGS = ["--max-line-length=120", "--extend-ignore=E203,W503"]
# CI check states that will not change again (anything else counts as still-running).
_TERMINAL = {"pass", "fail", "error", "skipping", "cancelled", "neutral"}


def _run(cmd, **kw):
    return subprocess.run(cmd, **kw)


def _repo_root():
    r = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
    )
    return r.stdout.strip() or "."


def _gh_checks(pr):
    """Return [(name, status)] parsed from `gh pr checks <pr>` (tab-separated)."""
    r = subprocess.run(["gh", "pr", "checks", str(pr)], capture_output=True, text=True)
    rows = []
    for line in (r.stdout or "").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].strip():
            rows.append((parts[0].strip(), parts[1].strip().lower()))
    return rows


def cmd_ci(args):
    pr = args.pr
    for _ in range(90):  # ~30 min backstop at 20s/poll
        rows = _gh_checks(pr)
        failing = [n for n, s in rows if s in ("fail", "error")]
        pending = [n for n, s in rows if s and s not in _TERMINAL]
        if rows and failing:
            print(f"PR #{pr}: FAILING")
            for n in failing:
                print(f"  ✗ {n}")
            return 1
        if rows and not pending:
            print(f"PR #{pr}: ALL GREEN ({len(rows)} checks)")
            return 0
        if not args.watch:
            if pending:
                print(f"PR #{pr}: pending — {', '.join(pending)}")
            else:
                print(f"PR #{pr}: no checks reported yet")
            return 2
        time.sleep(20)
    print(f"PR #{pr}: still pending after timeout")
    return 2


def cmd_lint(args):
    paths = args.paths
    fail = 0
    for tool, cmd in [
        ("black", [sys.executable, "-m", "black", "--check", *paths]),
        ("isort", [sys.executable, "-m", "isort", "--check-only", *paths]),
        ("flake8", [sys.executable, "-m", "flake8", *paths, *FLAKE8_FLAGS]),
    ]:
        print(f"== {tool} ==")
        if _run(cmd).returncode != 0:
            fail = 1
    print("LINT OK" if not fail else "LINT FAILED")
    return fail


def cmd_mypy(args):
    root = _repo_root()
    svc_dir = f"{root}/src/services/{args.service}"
    return _run(
        [
            sys.executable,
            "-m",
            "mypy",
            ".",
            "--ignore-missing-imports",
            "--config-file",
            f"{root}/pyproject.toml",
        ],
        cwd=svc_dir,
    ).returncode


def cmd_test(args):
    root = _repo_root()
    target = args.pytest_args or ["tests/unit"]
    return _run([sys.executable, "-m", "pytest", "-q", *target], cwd=root).returncode


def main():
    p = argparse.ArgumentParser(prog="dev.py", description="Minder dev-loop helpers")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("ci", help="CI status verdict for a PR")
    c.add_argument("pr")
    c.add_argument(
        "--watch",
        action="store_true",
        help="poll until all checks reach a terminal state",
    )
    c.set_defaults(func=cmd_ci)

    lint = sub.add_parser("lint", help="black --check + isort + flake8 (CI flags)")
    lint.add_argument("paths", nargs="+")
    lint.set_defaults(func=cmd_lint)

    m = sub.add_parser("mypy", help="per-service mypy with the repo config")
    m.add_argument("service", help="service dir name under src/services/")
    m.set_defaults(func=cmd_mypy)

    t = sub.add_parser("test", help="run unit tests (tests/unit by default)")
    t.add_argument("pytest_args", nargs="*")
    t.set_defaults(func=cmd_test)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
