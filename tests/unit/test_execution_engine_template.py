"""Unit tests for the webhook TemplateEngine (`plugin-registry/core/execution_engine`).

This is the platform's "no arbitrary code execution" boundary: plugin webhooks
render fixed ``{{ .field }}`` templates against the payload — field extraction only,
never eval/exec. It had no unit coverage. These lock the SECURITY property (a
template without the required leading dot, or an expression, is NOT evaluated — it
passes through literally or resolves to a plain dict lookup) plus the normal render
contract.

`execution_engine` imports only stdlib + httpx, so it loads by path with no injection.
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
    / "execution_engine.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("execution_engine_under_test", _MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TE = _load().TemplateEngine


# ── render: normal substitution ─────────────────────────────────────────────
def test_render_simple_field():
    assert TE.render("hi {{ .name }}", {"name": "bob"}) == "hi bob"


def test_render_nested_field():
    assert TE.render("{{ .author.username }}", {"author": {"username": "al"}}) == "al"


def test_render_coerces_non_string_value():
    assert TE.render("n={{ .count }}", {"count": 7}) == "n=7"


def test_render_missing_field_raises():
    with pytest.raises(ValueError):
        TE.render("{{ .nope }}", {"name": "bob"})


# ── SECURITY: no code execution ─────────────────────────────────────────────
@pytest.mark.parametrize(
    "template",
    [
        "{{ 7 * 7 }}",  # no leading dot → not a placeholder
        "{{ __import__('os').system('x') }}",  # no leading dot → literal
        "${name}",  # not our syntax
        "{{name}}",  # missing the required dot
        "plain text",
    ],
)
def test_non_dotted_templates_pass_through_literally(template):
    # The pattern requires `{{ .field }}` — anything else is left untouched, so no
    # expression is ever evaluated.
    assert TE.render(template, {"name": "x", "os": "y"}) == template


def test_dotted_lookup_is_pure_dict_access_not_attribute_access():
    # A dunder-looking field name is just a dict key lookup (missing → ValueError),
    # never Python attribute access — so no object internals are reachable.
    with pytest.raises(ValueError):
        TE.render("{{ .__class__ }}", {"name": "x"})


# ── _get_nested_value ───────────────────────────────────────────────────────
def test_get_nested_value_missing_returns_none():
    assert TE._get_nested_value({"a": {"b": 1}}, "a.c") is None


def test_get_nested_value_through_non_dict_returns_none():
    assert TE._get_nested_value({"a": 5}, "a.b") is None


# ── render_dict: recursive, passes non-strings through ───────────────────────
def test_render_dict_recurses_and_preserves_non_strings():
    out = TE.render_dict(
        {"greet": "hi {{ .name }}", "nested": {"u": "{{ .name }}"}, "n": 3},
        {"name": "bob"},
    )
    assert out == {"greet": "hi bob", "nested": {"u": "bob"}, "n": 3}
