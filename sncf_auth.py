"""
Authentification SNCF Connect via Auth0.
Gère login, refresh de token, et récupération du profil (carte TGV Max).
"""
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

_AUTH0 = "https://auth.monidentifiant.sncf"
_CLIENT_ID = "mkEcrPWwH3EWhEvxBbZCjpHHVo6oJZlX"
_AUDIENCE = "https://www.sncf-connect.com/bff/api/v2/"
_SCOPE = "openid profile email offline_access entity_id:01002"

BFF_KEY = os.environ.get("SNCF_BFF_KEY", "ah1MPO-izehIHD-QZZ9y88n-kku876")

BFF_HEADERS = {
    "x-bff-key": BFF_KEY,
    "x-client-app-id": "front-web",
    "x-client-channel": "web",
    "x-market-locale": "fr_FR",
    "x-api-env": "production",
    "virtual-env-name": "master",
    "x-app-version": "767c8d4792",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/147.0.0.0 Safari/537.36"
    ),
}


async def login_sncf(email: str, password: str) -> dict:
    """
    Authentifie l'utilisateur via Auth0 (ROPC flow).
    Retourne tokens + profil (customer_id, card_number, date_of_birth).
    """
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{_AUTH0}/oauth/token",
            json={
                "grant_type": "password",
                "username": email,
                "password": password,
                "client_id": _CLIENT_ID,
                "scope": _SCOPE,
                "audience": _AUDIENCE,
            },
        )
        if r.status_code != 200:
            print(f"[SNCF Auth] Erreur Auth0 ({r.status_code}): {r.text[:500]}")
            raise ValueError(f"Erreur Auth0 ({r.status_code}): {r.text[:300]}")
        tokens = r.json()

    access_token = tokens["access_token"]
    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in", 1800)

    profile = await _fetch_profile(access_token)

    now = datetime.now(timezone.utc)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_expires_at": (now + timedelta(seconds=expires_in)).isoformat(),
        "refresh_expires_at": (now + timedelta(days=30)).isoformat(),
        **profile,
    }


async def refresh_access_token(refresh_tok: str) -> dict:
    """Renouvelle l'access token avec le refresh token."""
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{_AUTH0}/oauth/token",
            json={
                "grant_type": "refresh_token",
                "refresh_token": refresh_tok,
                "client_id": _CLIENT_ID,
            },
        )
        if r.status_code != 200:
            raise ValueError(f"Refresh échoué ({r.status_code}): {r.text[:200]}")
        tokens = r.json()

    now = datetime.now(timezone.utc)
    return {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token", refresh_tok),
        "token_expires_at": (now + timedelta(seconds=tokens.get("expires_in", 1800))).isoformat(),
    }


async def _fetch_profile(access_token: str) -> dict:
    """Récupère le profil SNCF : customer_id, carte TGV Max, date de naissance."""
    headers = {**BFF_HEADERS, "Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(
            "https://www.sncf-connect.com/bff/api/v2/account",
            headers=headers,
        )
        if r.status_code != 200:
            print(f"[SNCF Auth] Profil non récupéré ({r.status_code}): {r.text[:300]}")
            return {"customer_id": None, "card_number": None, "card_label": "MAX JEUNE", "date_of_birth": None}
        data = r.json()

    print(f"[SNCF Auth] Profil brut (extrait): {str(data)[:500]}")

    customer_id = data.get("customerId") or data.get("id")
    dob = data.get("dateOfBirth", "")
    first_name = data.get("firstName", "")
    last_name = data.get("lastName", "")
    initials = (first_name[:1] + last_name[:1]).upper()

    card = None
    for dc in data.get("discountCards", []):
        if dc.get("code") in ("TGV_MAX", "HAPPY_CARD"):
            card = dc
            break

    return {
        "customer_id": customer_id,
        "card_number": card.get("number") if card else None,
        "card_label": card.get("label", "MAX JEUNE") if card else "MAX JEUNE",
        "date_of_birth": dob,
        "first_name": first_name,
        "last_name": last_name,
        "initials": initials,
    }


async def get_station_id(name: str, access_token: Optional[str] = None) -> Optional[str]:
    """Recherche l'ID RESARAIL d'une gare par son nom."""
    headers = {**BFF_HEADERS}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            "https://www.sncf-connect.com/bff/api/v1/autocomplete",
            headers=headers,
            params={"term": name, "lang": "fr_FR", "context": "TRIP"},
        )
        if r.status_code != 200:
            print(f"[SNCF Auth] Autocomplete échoué ({r.status_code}): {r.text[:200]}")
            return None
        results = r.json()

    print(f"[SNCF Auth] Autocomplete '{name}': {str(results)[:300]}")

    # Format typique : liste de {id, label, ...}
    if isinstance(results, list) and results:
        return results[0].get("id")
    if isinstance(results, dict):
        items = results.get("places") or results.get("results") or results.get("data") or []
        if items:
            return items[0].get("id")
    return None
