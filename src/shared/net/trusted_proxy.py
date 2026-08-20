"""Trusted-proxy real-client-IP resolution (#749 / #716).

Every external request reaches a Minder service through Traefik (and, for the
api-gateway, potentially through the gateway's own proxy too). At each hop the
peer we actually connect to (`request.client.host`) is the *proxy*, not the real
external client — so any rate-limit key or access log that trusts
`request.client.host` collapses every real caller behind the proxy into a single
identity (the proxy's container IP). That's exactly what made the per-client
limit on `/v1/auth/register` / `/v1/auth/login` one shared global bucket (#749).

The real client IP lives in the `X-Forwarded-For` (XFF) header, but that header
is **client-controllable** — a request can arrive with a forged XFF. Trusting it
blindly would let anyone spoof their apparent IP and dodge (or poison) IP-based
limits. The safe, standard mechanism (and the one chosen for #749) is a
**trusted-proxy CIDR allowlist**: only honour XFF when the immediate peer is
itself a known proxy (its address falls inside a configured trusted CIDR), and
then walk the chain from the right, peeling off trusted-proxy hops until the
first address that is NOT a trusted proxy — that is the real client. If the peer
is not trusted, XFF is ignored entirely and the peer address is used as-is.

Config is a comma-separated CIDR list in the ``TRUSTED_PROXY_CIDRS`` env var. The
default trusts loopback (the api-gateway's own `127.0.0.1:8000` host-port path,
called out in #749) plus the RFC1918 ranges Docker's default bridge pool draws
from — `minder-network` has no pinned subnet, so an exact Traefik IP isn't stable
across restarts, which is precisely why a CIDR (not a fixed IP) was chosen.
Operators who put the stack on a known subnet can tighten this to just that CIDR.
"""

import ipaddress
import os
from typing import List, Optional, Sequence, Union

from fastapi import Request

# Loopback covers the api-gateway's own loopback host-port (127.0.0.1:8000, #749);
# the RFC1918 ranges cover Docker's default bridge/overlay address pools, where
# Traefik and the inter-service network live. Deliberately broad-but-private: it
# trusts only non-routable addresses, never a public source, so it can't be
# reached (and thus can't be spoofed) from outside the host/compose network.
DEFAULT_TRUSTED_PROXY_CIDRS = (
    "127.0.0.0/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
)

_Network = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]


def parse_trusted_cidrs(csv: Optional[str]) -> List[_Network]:
    """Parse a comma-separated CIDR string into networks, skipping empty/invalid
    entries (a malformed operator value must never crash request handling — a
    bad entry is simply not trusted)."""
    if not csv:
        return []
    networks: List[_Network] = []
    for raw in csv.split(","):
        entry = raw.strip()
        if not entry:
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            # Ignore a malformed CIDR rather than fail closed-and-crash.
            continue
    return networks


def _is_trusted(ip_str: str, trusted: Sequence[_Network]) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str.strip())
    except ValueError:
        return False
    return any(ip in network for network in trusted)


def resolve_client_ip(
    request: Request,
    trusted_cidrs: Optional[Sequence[_Network]] = None,
) -> str:
    """Return the real client IP for ``request`` using trusted-proxy rules (#749).

    - ``request.client.host`` is the immediate peer. If it isn't in a trusted
      CIDR (or there's no XFF header), it IS the client we key on — XFF is
      ignored, so a forged header on a direct connection can't spoof the IP.
    - If the peer is trusted, walk ``X-Forwarded-For`` right-to-left, skipping
      addresses that are themselves trusted proxies; the first non-trusted
      address is the real client. If every hop is trusted (or the chain is
      empty), fall back to the left-most XFF entry, then to the peer.

    ``trusted_cidrs`` defaults to ``parse_trusted_cidrs(os.environ[
    "TRUSTED_PROXY_CIDRS"])`` (or the module default) so callers without a
    settings object — e.g. the shared ``enforce_rate_limit`` decorator running
    inside every downstream service — get correct behaviour with no wiring.
    """
    if trusted_cidrs is None:
        trusted_cidrs = parse_trusted_cidrs(
            os.environ.get("TRUSTED_PROXY_CIDRS", DEFAULT_TRUSTED_PROXY_CIDRS)
        )

    peer = request.client.host if request.client else "127.0.0.1"

    xff = request.headers.get("X-Forwarded-For")
    if not xff or not _is_trusted(peer, trusted_cidrs):
        return peer

    # XFF is "client, proxy1, proxy2, ..." (left = original client, each proxy
    # appends the address it received the connection from). Peel trusted hops
    # off the right; the first non-trusted address is the client.
    forwarded = [part.strip() for part in xff.split(",") if part.strip()]
    for candidate in reversed(forwarded):
        if not _is_trusted(candidate, trusted_cidrs):
            # Validate before trusting it as an IP; a garbage value falls through.
            try:
                ipaddress.ip_address(candidate)
            except ValueError:
                continue
            return candidate

    # Everything in the chain is a trusted proxy (or empty/garbage): the
    # left-most entry is the best available "client" answer; else the peer.
    return forwarded[0] if forwarded else peer
