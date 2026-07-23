#!/usr/bin/env python3
"""Check pinned Python dependencies across the services for available PyPI updates.

Companion to the Docker image auto-update (#96 report) for the Python side (#34: track
the plugin libs' — e.g. tefas-crawler, borsapy — versions too). Scans every
``src/**/requirements.txt``, reads each ``name[extras]==version`` pin, asks the PyPI
JSON API for the latest stable release, and prints a Markdown report of what's
outdated (classified patch/minor/major). Read-only; stdlib only (urllib) so it runs
anywhere without extra deps.

Usage:
    python scripts/check_pip_updates.py [--out report.md]
"""

import argparse
import glob
import json
import re
import sys
import urllib.request
from typing import Dict, List, Optional, Tuple

PIN_RE = re.compile(r"^([A-Za-z0-9_.\-]+)(\[[^\]]+\])?==([0-9][0-9A-Za-z.\-]*)\s*(#.*)?$")


def find_requirements() -> List[str]:
    return sorted(glob.glob("src/**/requirements.txt", recursive=True))


def parse_pins(path: str) -> List[Tuple[str, str, str]]:
    """Return [(package, extras_or_'', pinned_version)] for exact-pinned lines."""
    pins = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            m = PIN_RE.match(line)
            if m:
                pins.append((m.group(1), m.group(2) or "", m.group(3)))
    return pins


def latest_stable(package: str, timeout: float = 15.0) -> Optional[str]:
    """Latest stable version from PyPI (skips pre-releases). None on error."""
    url = f"https://pypi.org/pypi/{package}/json"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # nosec B310
            data = json.load(resp)
    except Exception:
        return None
    releases = data.get("releases") or {}
    stable = [
        v
        for v in releases
        if re.fullmatch(r"[0-9]+(\.[0-9]+)*", v) and releases[v]
    ]
    if stable:
        return max(stable, key=lambda v: [int(p) for p in v.split(".")])
    return (data.get("info") or {}).get("version")


def _tuple(v: str) -> Tuple[int, ...]:
    out = []
    for p in v.split("."):
        try:
            out.append(int(p))
        except ValueError:
            out.append(0)
    return tuple(out)


def classify(cur: str, latest: str) -> str:
    c, latest_t = _tuple(cur), _tuple(latest)
    c += (0,) * (3 - len(c))
    latest_t += (0,) * (3 - len(latest_t))
    if latest_t[0] != c[0]:
        return "major"
    if latest_t[1] != c[1]:
        return "minor"
    return "patch"


def build_report() -> str:
    # package -> {version -> [files]} ; and the resolved latest
    pkgs: Dict[str, Dict[str, List[str]]] = {}
    extras: Dict[str, str] = {}
    for path in find_requirements():
        short = path.replace("\\", "/").replace("src/services/", "").replace(
            "/requirements.txt", ""
        )
        for pkg, extra, ver in parse_pins(path):
            key = pkg.lower()
            pkgs.setdefault(key, {}).setdefault(ver, []).append(short)
            if extra:
                extras[key] = extra

    outdated, current, unknown = [], [], []
    for key in sorted(pkgs):
        latest = latest_stable(key)
        display = key + extras.get(key, "")
        for ver, files in sorted(pkgs[key].items()):
            where = ", ".join(sorted(set(files)))
            if latest is None:
                unknown.append(f"- **{display}** `{ver}` — PyPI lookup failed ({where})")
            elif _tuple(ver) < _tuple(latest):
                outdated.append(
                    f"- **{display}**: `{ver}` → `{latest}` "
                    f"[{classify(ver, latest)}] ({where})"
                )
            else:
                current.append(f"- **{display}** `{ver}` ({where})")

    lines = ["# Python Dependency Updates Report", ""]
    lines.append(f"## ⬆️ Updates available ({len(outdated)})")
    lines += (outdated or ["- none"]) + [""]
    lines.append(f"## ✅ Up to date ({len(current)})")
    lines += (current or ["- none"]) + [""]
    if unknown:
        lines.append(f"## 🔍 Could not check ({len(unknown)})")
        lines += unknown + [""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="write the Markdown report to this file too")
    args = ap.parse_args()
    # Report contains emoji; force UTF-8 stdout so it prints on any console (Windows
    # cp125x included), matching the UTF-8 CI environment.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    report = build_report()
    print(report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
