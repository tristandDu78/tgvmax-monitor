"""
Accès au dataset TGV Max via l'Open Data SNCF.
Endpoint : https://ressources.data.sncf.com/api/explore/v2.1/catalog/datasets/tgvmax/records

Champs utilisés :
  origine        - nom de la gare de départ
  destination    - nom de la gare d'arrivée
  date           - date du train (YYYY-MM-DD)
  heure_depart   - heure de départ (HH:MM ou HH:MM:SS)
  heure_arrivee  - heure d'arrivée
  train_no       - numéro du train
  od_happy_card  - "OUI" si place TGV Max disponible
"""
import asyncio
from typing import Dict, List

import httpx

_API = "https://ressources.data.sncf.com/api/explore/v2.1/catalog/datasets/tgvmax/records"

_gares_cache: List[str] = []


async def refresh_gares_cache() -> None:
    """Reconstruit la liste de toutes les gares (origines + destinations)."""
    global _gares_cache
    gares: set[str] = set()
    async with httpx.AsyncClient(timeout=30) as c:
        for field in ("origine", "destination"):
            r = await c.get(
                _API,
                params={"select": field, "group_by": field, "limit": 500},
            )
            if r.status_code == 200:
                for rec in r.json().get("results", []):
                    val = rec.get(field)
                    if val:
                        gares.add(val.strip())
    _gares_cache = sorted(gares)
    print(f"[OpenData] Cache gares mis à jour : {len(_gares_cache)} gares")


async def get_gares(query: str = "") -> List[str]:
    """Retourne les gares correspondant à la requête (autocomplétion)."""
    if not _gares_cache:
        await refresh_gares_cache()
    q = query.upper().strip()
    if not q:
        return _gares_cache[:50]
    return [g for g in _gares_cache if q in g.upper()][:20]


async def check_trains_opendata(
    origin: str,
    destination: str,
    travel_date: str,
    time_from: str,
    time_to: str,
) -> List[Dict]:
    """
    Interroge l'open data et retourne les trains TGV Max disponibles
    correspondant aux critères (date + créneau horaire).
    """
    where = (
        f'origine="{origin}" AND destination="{destination}" '
        f'AND date=date\'{travel_date}\' AND od_happy_card="OUI"'
    )
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(_API, params={"where": where, "limit": 100})
        if r.status_code != 200:
            print(f"[OpenData] Erreur API SNCF : {r.status_code}")
            return []
        results = r.json().get("results", [])

    trains = []
    for rec in results:
        dep = (rec.get("heure_depart") or "")[:5]  # HH:MM
        arr = (rec.get("heure_arrivee") or "")[:5]
        if not dep:
            continue
        if time_from <= dep <= time_to:
            trains.append(
                {
                    "train_no": str(rec.get("train_no", "?")),
                    "origin": rec.get("origine", origin),
                    "destination": rec.get("destination", destination),
                    "date": travel_date,
                    "departure": dep,
                    "arrival": arr,
                }
            )
    return trains
