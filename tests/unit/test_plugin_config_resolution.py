"""Unit tests for central plugin config resolution (`plugin-registry/core/plugin_config`).

This is the shared default → env → persisted resolution + secret-masking + PUT-body
validation used by both the loader and the config API (#34). It was only covered by a
skip-in-CI integration test; these lock the contract (resolution order, type coercion,
secret masking, validation) in the unit suite.

Loaded by path — the module imports only stdlib, so no fake-injection is needed
(unlike other hyphenated-service modules that pull `config`/`models`).
"""

import importlib.util
from pathlib import Path

import pytest

_MOD = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "plugin-registry"
    / "core"
    / "plugin_config.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("plugin_config_under_test", _MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pc = _load()


class _FakePlugin:
    CONFIG_SCHEMA = [
        {"key": "SYMBOLS", "type": "string", "default": "BTC"},
        {"key": "MAX_ITEMS", "type": "int", "default": 10},
        {"key": "ENABLED", "type": "bool", "default": False},
        {"key": "API_KEY", "type": "string", "default": "", "secret": True},
    ]

    def __init__(self):
        self.applied = None

    def apply_config(self, cfg):
        self.applied = cfg


class _SchemalessPlugin:
    pass


# ── _coerce ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "value,typ,expected",
    [
        ("5", "int", 5),
        ("2.5", "float", 2.5),
        ("true", "bool", True),
        ("off", "bool", False),
        (True, "bool", True),
        (7, "string", "7"),
        (None, "int", None),
    ],
)
def test_coerce_types(value, typ, expected):
    assert pc._coerce(value, typ) == expected


def test_coerce_bad_value_falls_back_to_original():
    # Uncoercible int → returned verbatim, not crashed.
    assert pc._coerce("not-a-number", "int") == "not-a-number"


# ── effective_config: default → env → persisted ─────────────────────────────
def test_defaults_when_nothing_set():
    cfg = pc.effective_config(_FakePlugin(), {})
    assert cfg == {"SYMBOLS": "BTC", "MAX_ITEMS": 10, "ENABLED": False, "API_KEY": ""}


def test_env_overrides_default(monkeypatch):
    monkeypatch.setenv("SYMBOLS", "ETH")
    monkeypatch.setenv("MAX_ITEMS", "25")
    cfg = pc.effective_config(_FakePlugin(), {})
    assert cfg["SYMBOLS"] == "ETH"
    assert cfg["MAX_ITEMS"] == 25  # coerced to int


def test_persisted_wins_over_env(monkeypatch):
    monkeypatch.setenv("SYMBOLS", "ETH")
    cfg = pc.effective_config(_FakePlugin(), {"SYMBOLS": "SOL"})
    assert cfg["SYMBOLS"] == "SOL"


def test_schemaless_plugin_resolves_empty():
    assert pc.effective_config(_SchemalessPlugin(), {}) == {}
    assert pc.get_schema(_SchemalessPlugin()) == []


# ── apply_effective ─────────────────────────────────────────────────────────
def test_apply_effective_pushes_into_instance():
    plugin = _FakePlugin()
    cfg = pc.apply_effective(plugin, {"SYMBOLS": "SOL"})
    assert cfg["SYMBOLS"] == "SOL"
    assert plugin.applied == cfg  # apply_config was called with the effective config


def test_apply_effective_noop_without_schema():
    plugin = _SchemalessPlugin()
    assert pc.apply_effective(plugin, {}) == {}


# ── mask_secrets ────────────────────────────────────────────────────────────
def test_mask_secrets_redacts_nonempty_secret():
    masked = pc.mask_secrets(_FakePlugin(), {"SYMBOLS": "BTC", "API_KEY": "s3cr3t"})
    assert masked == {"SYMBOLS": "BTC", "API_KEY": "***"}


def test_mask_secrets_leaves_empty_secret_visible():
    # Empty/None secret isn't redacted (nothing to hide) — documents current behavior.
    masked = pc.mask_secrets(_FakePlugin(), {"API_KEY": ""})
    assert masked == {"API_KEY": ""}


# ── validate_update ─────────────────────────────────────────────────────────
def test_validate_rejects_non_dict():
    ok, msg = pc.validate_update(_FakePlugin(), ["not", "a", "dict"])
    assert not ok and "JSON object" in msg


def test_validate_rejects_unknown_key():
    ok, msg = pc.validate_update(_FakePlugin(), {"NOPE": 1})
    assert not ok and "unknown config key" in msg


def test_validate_rejects_bad_int():
    ok, msg = pc.validate_update(_FakePlugin(), {"MAX_ITEMS": "banana"})
    assert not ok and "must be int" in msg


def test_validate_accepts_valid_and_empty():
    assert pc.validate_update(_FakePlugin(), {"MAX_ITEMS": "5", "SYMBOLS": "x"}) == (
        True,
        "",
    )
    assert pc.validate_update(_FakePlugin(), {}) == (True, "")
