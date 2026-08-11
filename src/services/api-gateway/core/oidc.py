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
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException
from jose import jwk, jwt

from config import settings

logger = logging.getLogger("minder.api-gateway")

_DISCOVERY_PATH = "/.well-known/openid-configuration"

# authelia.minder.local only resolves via Traefik, which api-gateway's own
# container can't reach (it's on the same internal docker network as
# Authelia, not the host's network Traefik sits on). Every call below
# connects to the internal container address instead, but sends these
# headers so Authelia's own responses -- issuer, token_endpoint, jwks_uri,
# and the iss claim on issued ID tokens -- stay the public hostname the
# browser and this module's own issuer/audience checks both expect. Host
# alone isn't enough: confirmed empirically against a real Authelia
# instance (plain Host -> 400, adding X-Forwarded-Proto/-Host -> 200) --
# Authelia's OIDC endpoints specifically require the forwarded-proto/host
# pair Traefik would normally add, not just a bare Host header.
_parsed_issuer = urlparse(settings.AUTHELIA_ISSUER_URL)
_AUTHELIA_FORWARDED_HEADERS = {
    "Host": _parsed_issuer.netloc,
    "X-Forwarded-Proto": _parsed_issuer.scheme,
    "X-Forwarded-Host": _parsed_issuer.netloc,
}


async def _discover() -> Dict[str, Any]:
    """Fetch Authelia's OIDC discovery document. Not cached: this is only
    called once per login (a handful of requests a day on a self-hosted
    platform), and always reflects Authelia's current config immediately
    if it ever changes -- not worth the staleness risk for the request rate
    involved."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{settings.AUTHELIA_INTERNAL_URL}{_DISCOVERY_PATH}",
            headers=_AUTHELIA_FORWARDED_HEADERS,
        )
    resp.raise_for_status()
    return resp.json()


def _internalize(url: str) -> str:
    """Discovery returns public https://authelia.minder.local/... URLs (by
    design -- those are what a browser would use); rewrite them back to the
    internal address for api-gateway's own follow-up calls, same as
    _discover's own request above."""
    parsed = urlparse(url)
    return url.replace(
        f"{parsed.scheme}://{parsed.netloc}", settings.AUTHELIA_INTERNAL_URL
    )


async def exchange_code_for_tokens(code: str) -> Dict[str, str]:
    """POST the authorization code to Authelia's token endpoint using this
    client's confidential client_secret (never exposed to the browser) and
    return the raw (still-unverified) {id_token, access_token} pair -- both
    are needed by verify_id_token below, since the ID token carries an
    at_hash claim binding it to this specific access token.

    Authenticates via HTTP Basic (client_secret_basic) -- the OIDC-spec
    default a confidential client falls back to when no auth method is
    declared -- rather than putting the secret in the POST body
    (client_secret_post). Declaring client_secret_post explicitly on the
    Authelia side did not work in practice (confirmed against a real
    instance: still rejected as "does not allow this method" after
    restarting with the change in place), so this uses the method Authelia
    already accepts without any extra client config.
    """
    discovery = await _discover()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            _internalize(discovery["token_endpoint"]),
            headers=_AUTHELIA_FORWARDED_HEADERS,
            auth=(settings.MINDER_OIDC_CLIENT_ID, settings.MINDER_OIDC_CLIENT_SECRET),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.MINDER_OIDC_REDIRECT_URI,
            },
        )
    if resp.status_code != 200:
        logger.warning(f"OIDC token exchange failed: {resp.status_code} {resp.text}")
        raise HTTPException(status_code=502, detail="OIDC token exchange failed")
    body = resp.json()
    id_token = body.get("id_token")
    access_token = body.get("access_token")
    if not id_token or not access_token:
        raise HTTPException(status_code=502, detail="OIDC response missing tokens")
    return {"id_token": id_token, "access_token": access_token}


async def verify_id_token(
    id_token: str, access_token: str, expected_nonce: str
) -> Dict[str, Any]:
    """Verify the ID token's RS256 signature against Authelia's published
    JWKS, then its exp/aud/iss/at_hash (via jose's own checks -- at_hash
    needs access_token to compare against, hence the parameter) and nonce
    (manually -- jose does not treat nonce as a standard claim to validate
    itself).
    Returns the verified claim set."""
    discovery = await _discover()
    async with httpx.AsyncClient(timeout=10.0) as client:
        jwks_resp = await client.get(
            _internalize(discovery["jwks_uri"]),
            headers=_AUTHELIA_FORWARDED_HEADERS,
        )
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
            access_token=access_token,
        )
    except Exception as e:
        logger.warning(f"OIDC id_token verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid OIDC identity token")

    if claims.get("nonce") != expected_nonce:
        raise HTTPException(status_code=401, detail="OIDC nonce mismatch")

    return claims


async def fetch_userinfo(access_token: str) -> Dict[str, Any]:
    """Fetch the /userinfo claims for the token holder. Authelia's ID token
    only carries a handful of claims by default (confirmed against a real
    instance: the `sub` claim came back as an opaque per-client UUID, with
    no preferred_username/groups at all even though the profile/groups
    scopes were requested and granted) -- preferred_username, email, and
    groups all live here instead, the standard OIDC place for anything
    beyond the bare identity claims. Best-effort: a failure here shouldn't
    block login, since verify_id_token already established who the caller
    is via the id_token's own (verified) sub claim."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{settings.AUTHELIA_INTERNAL_URL}/api/oidc/userinfo",
            headers={
                **_AUTHELIA_FORWARDED_HEADERS,
                "Authorization": f"Bearer {access_token}",
            },
        )
    if resp.status_code != 200:
        logger.warning(f"OIDC userinfo fetch failed: {resp.status_code} {resp.text}")
        return {}
    return resp.json()
