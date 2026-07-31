"""Unit tests for crypto/tefas influx symbol/code validation (#215 L3).

Symbols (crypto ``CRYPTO_SYMBOLS``) and fund codes (tefas ``TEFAS_FUNDS``) are
API-settable via the JWT-gated PUT /config and get interpolated into an InfluxDB SQL
query + line protocol. These lock the safe-charset guard that stops a config value
from breaking out into injection (or corrupting line protocol with a space/comma).
"""

import pytest

from plugins.crypto import _SAFE_SYMBOL
from plugins.tefas import _SAFE_CODE

_SAFE = ["BTC", "ETH", "BTC-USD", "AFA", "X_1.2", "a.b-c_d"]
_UNSAFE = [
    "BTC'; DROP TABLE x --",  # SQL breakout
    "sym' OR '1'='1",
    "a b",  # space breaks line protocol
    "x,y",  # comma breaks line protocol tag set
    "a=b",  # '=' breaks line protocol
    "",  # empty
    "a\nb",  # newline (multi-line injection)
    "évil",  # non-ascii
]


@pytest.mark.parametrize("pattern", [_SAFE_SYMBOL, _SAFE_CODE])
@pytest.mark.parametrize("value", _SAFE)
def test_safe_values_accepted(pattern, value):
    assert pattern.match(value)


@pytest.mark.parametrize("pattern", [_SAFE_SYMBOL, _SAFE_CODE])
@pytest.mark.parametrize("value", _UNSAFE)
def test_injection_values_rejected(pattern, value):
    assert not pattern.match(value)
