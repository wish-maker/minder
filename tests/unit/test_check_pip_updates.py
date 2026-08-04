"""Unit tests for scripts/check_pip_updates.py's pure parsing/classification
logic (pin parsing, version-tuple comparison, update classification, report
building). No network: latest_stable is monkeypatched wherever build_report
is exercised.
"""

from scripts.check_pip_updates import _tuple, build_report, classify, parse_pins


def test_parse_pins_basic(tmp_path):
    reqs = tmp_path / "requirements.txt"
    reqs.write_text("fastapi==0.115.0\nuvicorn==0.30.1\n")
    assert parse_pins(str(reqs)) == [
        ("fastapi", "", "0.115.0"),
        ("uvicorn", "", "0.30.1"),
    ]


def test_parse_pins_with_extras(tmp_path):
    reqs = tmp_path / "requirements.txt"
    reqs.write_text("uvicorn[standard]==0.30.1\n")
    assert parse_pins(str(reqs)) == [("uvicorn", "[standard]", "0.30.1")]


def test_parse_pins_skips_comments_blank_and_dash_lines(tmp_path):
    reqs = tmp_path / "requirements.txt"
    reqs.write_text(
        "# a comment\n" "\n" "-r base.txt\n" "fastapi==0.115.0  # trailing comment\n"
    )
    assert parse_pins(str(reqs)) == [("fastapi", "", "0.115.0")]


def test_parse_pins_ignores_non_exact_pins(tmp_path):
    reqs = tmp_path / "requirements.txt"
    reqs.write_text("fastapi>=0.100.0\nuvicorn~=0.30\nlocust==2.31.1\n")
    assert parse_pins(str(reqs)) == [("locust", "", "2.31.1")]


def test_tuple_helper():
    assert _tuple("1.2.3") == (1, 2, 3)
    assert _tuple("1.2") == (1, 2)
    assert _tuple("not-a-version") == (0,)


def test_classify_patch_minor_major():
    assert classify("1.2.3", "1.2.4") == "patch"
    assert classify("1.2.3", "1.3.0") == "minor"
    assert classify("1.2.3", "2.0.0") == "major"


def test_classify_pads_short_versions():
    assert classify("1.2", "1.2.1") == "patch"
    assert classify("1", "2") == "major"


def test_build_report_categorizes_outdated_current_and_unknown(monkeypatch):
    monkeypatch.setattr(
        "scripts.check_pip_updates.find_requirements",
        lambda: ["src/services/fake-svc/requirements.txt"],
    )
    monkeypatch.setattr(
        "scripts.check_pip_updates.parse_pins",
        lambda path: [
            ("fastapi", "", "0.100.0"),
            ("uvicorn", "", "0.30.1"),
            ("mystery-pkg", "", "1.0.0"),
        ],
    )

    def fake_latest(pkg, timeout=15.0):
        return {"fastapi": "0.115.0", "uvicorn": "0.30.1"}.get(pkg)

    monkeypatch.setattr("scripts.check_pip_updates.latest_stable", fake_latest)

    report = build_report()

    assert "## ⬆️ Updates available (1)" in report
    assert "**fastapi**: `0.100.0` → `0.115.0` [minor]" in report
    assert "## ✅ Up to date (1)" in report
    assert "**uvicorn** `0.30.1`" in report
    assert "## 🔍 Could not check (1)" in report
    assert "**mystery-pkg** `1.0.0` — PyPI lookup failed" in report


def test_build_report_no_outdated_shows_none(monkeypatch):
    monkeypatch.setattr(
        "scripts.check_pip_updates.find_requirements",
        lambda: ["src/services/fake-svc/requirements.txt"],
    )
    monkeypatch.setattr(
        "scripts.check_pip_updates.parse_pins",
        lambda path: [("fastapi", "", "0.115.0")],
    )
    monkeypatch.setattr(
        "scripts.check_pip_updates.latest_stable", lambda pkg, timeout=15.0: "0.115.0"
    )

    report = build_report()

    assert "## ⬆️ Updates available (0)" in report
    assert "- none" in report
    assert "## 🔍 Could not check" not in report
