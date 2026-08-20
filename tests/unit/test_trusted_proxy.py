"""Unit tests for shared.net.trusted_proxy.resolve_client_ip (#749).

The trust boundary here is security-relevant: X-Forwarded-For is client-
controllable, so the resolver must only honour it when the immediate peer is a
configured trusted proxy, and must peel trusted-proxy hops off the chain to
recover the real client without ever trusting a forged value on a direct
connection.
"""

from unittest.mock import MagicMock

from shared.net.trusted_proxy import parse_trusted_cidrs, resolve_client_ip

TRUSTED = parse_trusted_cidrs("127.0.0.0/8,10.0.0.0/8,172.16.0.0/12")


def _request(peer, xff=None):
    req = MagicMock()
    req.client = MagicMock()
    req.client.host = peer
    headers = {}
    if xff is not None:
        headers["X-Forwarded-For"] = xff
    req.headers = headers
    return req


def test_no_client_defaults_to_loopback():
    req = MagicMock()
    req.client = None
    req.headers = {}
    assert resolve_client_ip(req, TRUSTED) == "127.0.0.1"


def test_untrusted_peer_ignores_xff():
    # A direct connection from a public client that forges XFF must NOT be able
    # to spoof its IP -- the peer address is used as-is.
    req = _request("203.0.113.9", xff="1.2.3.4")
    assert resolve_client_ip(req, TRUSTED) == "203.0.113.9"


def test_no_xff_returns_peer():
    req = _request("10.0.0.5")
    assert resolve_client_ip(req, TRUSTED) == "10.0.0.5"


def test_trusted_peer_single_client_in_xff():
    # Traefik (trusted) forwards the real client as the sole XFF entry.
    req = _request("172.18.0.2", xff="198.51.100.7")
    assert resolve_client_ip(req, TRUSTED) == "198.51.100.7"


def test_trusted_peer_peels_multiple_trusted_hops():
    # client, traefik, gateway -- both proxies trusted, peel to the client.
    req = _request("10.0.0.9", xff="198.51.100.7, 172.18.0.2, 10.0.0.9")
    assert resolve_client_ip(req, TRUSTED) == "198.51.100.7"


def test_spoofed_leading_entry_through_one_trusted_proxy_is_recovered():
    # Attacker sends "X-Forwarded-For: 9.9.9.9" to Traefik; Traefik appends the
    # real client. Peeling from the right yields the real client, not the forgery.
    req = _request("172.18.0.2", xff="9.9.9.9, 203.0.113.50")
    assert resolve_client_ip(req, TRUSTED) == "203.0.113.50"


def test_all_hops_trusted_falls_back_to_leftmost():
    req = _request("10.0.0.9", xff="10.1.1.1, 172.18.0.2, 10.0.0.9")
    assert resolve_client_ip(req, TRUSTED) == "10.1.1.1"


def test_garbage_xff_entry_is_skipped():
    req = _request("172.18.0.2", xff="not-an-ip, 203.0.113.7")
    assert resolve_client_ip(req, TRUSTED) == "203.0.113.7"


def test_parse_trusted_cidrs_skips_blank_and_invalid():
    nets = parse_trusted_cidrs("127.0.0.0/8, , garbage, 10.0.0.0/8")
    assert len(nets) == 2


def test_parse_trusted_cidrs_empty_string():
    assert parse_trusted_cidrs("") == []
    assert parse_trusted_cidrs(None) == []


def test_default_cidrs_from_env(monkeypatch):
    # With no explicit list, the helper reads TRUSTED_PROXY_CIDRS from the env.
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "192.168.0.0/16")
    trusted_peer = _request("192.168.1.10", xff="198.51.100.7")
    assert resolve_client_ip(trusted_peer) == "198.51.100.7"
    # 10.x is NOT in the env list now, so a 10.x peer is untrusted -> peer wins.
    untrusted_peer = _request("10.0.0.5", xff="198.51.100.7")
    assert resolve_client_ip(untrusted_peer) == "10.0.0.5"
