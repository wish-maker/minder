"""Authelia OIDC client (#<issue>) -- api-gateway is a confidential OIDC
client of Authelia's own provider (see docker/services/authelia/configuration.yml's
identity_providers.oidc block). This module only does the two things a
confidential client needs: exchange an authorization code for an ID token,
and verify that ID token's signature/claims. Minted-session bookkeeping
(mapping the verified identity to a Minder user, issuing Minder's own JWT)
stays in core/auth.py/routes/auth.py -- this module knows nothing about
Minder's own user table.
"""

import logging
from typing import Any, Dict

import httpx
from fastapi import HTTPException
from jose import jwk, jwt

from config import settings

logger = logging.getLogger("minder.api-gateway")

_DISCOVERY_PATH = "/.well-known/openid-configuration"


async def _discover() -> Dict[str, Any]:
    """Fetch Authelia's OIDC discovery document. Not cached: this is only
    called once per login (a handful of requests a day on a self-hosted
    platform), and always reflects Authelia's current config immediately
    if it ever changes -- not worth the staleness risk for the request rate
    involved."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{settings.AUTHELIA_ISSUER_URL}{_DISCOVERY_PATH}")
    resp.raise_for_status()
    return resp.json()


async def exchange_code_for_id_token(code: str) -> str:
    """POST the authorization code to Authelia's token endpoint using this
    client's confidential client_secret (never exposed to the browser) and
    return the raw (still-unverified) id_token string."""
    discovery = await _discover()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            discovery["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.MINDER_OIDC_REDIRECT_URI,
                "client_id": settings.MINDER_OIDC_CLIENT_ID,
                "client_secret": settings.MINDER_OIDC_CLIENT_SECRET,
            },
        )
    if resp.status_code != 200:
        logger.warning(f"OIDC token exchange failed: {resp.status_code} {resp.text}")
        raise HTTPException(status_code=502, detail="OIDC token exchange failed")
    body = resp.json()
    id_token = body.get("id_token")
    if not id_token:
        raise HTTPException(status_code=502, detail="OIDC response had no id_token")
    return id_token


async def verify_id_token(id_token: str, expected_nonce: str) -> Dict[str, Any]:
    """Verify the ID token's RS256 signature against Authelia's published
    JWKS, then its exp/aud/iss (via jose's own checks) and nonce (manually --
    jose does not treat nonce as a standard claim to validate itself).
    Returns the verified claim set."""
    discovery = await _discover()
    async with httpx.AsyncClient(timeout=10.0) as client:
        jwks_resp = await client.get(discovery["jwks_uri"])
    jwks_resp.raise_for_status()
    jwks = jwks_resp.json()

    unverified_header = jwt.get_unverified_header(id_token)
    kid = unverified_header.get("kid")
    matching_key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if matching_key is None:
        raise HTTPException(
            status_code=502, detail="OIDC signing key not found in JWKS"
        )
    public_key = jwk.construct(matching_key, "RS256")

    try:
        claims = jwt.decode(
            id_token,
            public_key,
            algorithms=["RS256"],
            audience=settings.MINDER_OIDC_CLIENT_ID,
            issuer=settings.AUTHELIA_ISSUER_URL,
        )
    except Exception as e:
        logger.warning(f"OIDC id_token verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid OIDC identity token")

    if claims.get("nonce") != expected_nonce:
        raise HTTPException(status_code=401, detail="OIDC nonce mismatch")

    return claims
