"""
Vérification en temps réel via l'API BFF de SNCF Connect.
Nécessite un compte SNCF Connect avec carte TGV Max.
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx

from sncf_auth import BFF_HEADERS, get_station_id

# Cache des IDs de gares pour éviter les appels répétés
_station_id_cache: Dict[str, str] = {}


async def _get_station_id_cached(name: str, access_token: Optional[str] = None) -> Optional[str]:
    if name not in _station_id_cache:
        sid = await get_station_id(name, access_token)
        if sid:
            _station_id_cache[name] = sid
    return _station_id_cache.get(name)


async def fetch_live(
    origin: str,
    destination: str,
    travel_date: str,
    time_from: str,
    time_to: str,
    sncf_account: Optional[dict] = None,
) -> List[Dict]:
    """
    Interroge l'API temps réel SNCF Connect.
    sncf_account doit contenir : access_token, customer_id, card_number,
    date_of_birth, card_label, first_name, last_name.
    Retourne [] si pas de compte SNCF ou si aucun train Max trouvé.
    """
    if not sncf_account or not sncf_account.get("access_token"):
        return []

    access_token = sncf_account["access_token"]
    customer_id = sncf_account.get("customer_id")
    card_number = sncf_account.get("card_number")
    dob = sncf_account.get("date_of_birth", "")
    card_label = sncf_account.get("card_label", "MAX JEUNE")
    first_name = sncf_account.get("first_name", "")
    last_name = sncf_account.get("last_name", "")
    initials = sncf_account.get("initials", "")

    if not card_number:
        print("[Live] Pas de carte TGV Max dans le profil SNCF.")
        return []

    # Résolution des IDs de gares
    origin_id = await _get_station_id_cached(origin, access_token)
    dest_id = await _get_station_id_cached(destination, access_token)

    if not origin_id or not dest_id:
        print(f"[Live] IDs de gares non trouvés : {origin} ({origin_id}), {destination} ({dest_id})")
        return []

    departure_dt = f"{travel_date}T04:00:00.000Z"

    try:
        birth_year = int(dob[:4]) if dob else 2000
        age = datetime.now(timezone.utc).year - birth_year
    except Exception:
        age = 21

    typology = "YOUNG" if age <= 27 else "SENIOR"

    payload = {
        "schedule": {
            "outward": {"date": departure_dt, "arrivalAt": False}
        },
        "mainJourney": {
            "origin": {"id": origin_id, "label": origin, "geolocation": False, "isEditable": True, "codes": []},
            "destination": {"id": dest_id, "label": destination, "geolocation": False, "isEditable": True, "codes": []},
        },
        "passengers": [{
            "id": str(uuid.uuid4()),
            "customerId": customer_id,
            "age": age,
            "dateOfBirth": dob,
            "discountCards": [{
                "code": "TGV_MAX",
                "number": card_number,
                "label": card_label,
                "selected": True,
                "storedInAccount": True,
            }],
            "typology": typology,
            "displayName": f"{first_name} {last_name}".strip(),
            "firstName": first_name,
            "lastName": last_name,
            "initials": initials,
            "withoutSeatAssignment": False,
            "hasDisability": False,
            "hasWheelchair": False,
        }],
        "pets": [],
        "itineraryId": str(uuid.uuid4()),
        "branch": "SHOP",
        "forceDisplayResults": True,
        "trainExpected": True,
        "wishBike": False,
        "strictMode": False,
        "directJourney": False,
        "transporterLabels": [],
        "userNavigation": ["IS_NOT_BUSINESS"],
    }

    headers = {
        **BFF_HEADERS,
        "Authorization": f"Bearer {access_token}",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                "https://www.sncf-connect.com/bff/api/v1/itineraries",
                headers=headers,
                json=payload,
            )
            if r.status_code != 200:
                print(f"[Live] Erreur API ({r.status_code}): {r.text[:300]}")
                return []
            data = r.json()
    except Exception as e:
        print(f"[Live] Exception: {e}")
        return []

    print(f"[Live] Réponse brute (extrait): {str(data)[:500]}")
    return _parse_itineraries(data, travel_date, time_from, time_to, origin, destination)


def _parse_itineraries(
    data: dict,
    travel_date: str,
    time_from: str,
    time_to: str,
    origin: str,
    destination: str,
) -> List[Dict]:
    """Extrait les trains TGV Max disponibles de la réponse API."""
    trains = []

    proposals = (
        data.get("journeys")
        or data.get("proposals")
        or data.get("itineraries")
        or data.get("results")
        or []
    )
    if not proposals and isinstance(data, list):
        proposals = data

    print(f"[Live] {len(proposals)} proposition(s) trouvée(s)")

    for prop in proposals:
        segments = prop.get("segments") or prop.get("legs") or prop.get("sections") or []
        if not segments and "departure" in prop:
            segments = [prop]

        for seg in segments:
            dep_str = seg.get("departure") or seg.get("departureDate") or seg.get("departureTime") or ""
            arr_str = seg.get("arrival") or seg.get("arrivalDate") or seg.get("arrivalTime") or ""
            train_no = str(seg.get("trainNumber") or seg.get("train_no") or seg.get("number") or "?")

            dep = dep_str[11:16] if len(dep_str) >= 16 else dep_str[:5]
            arr = arr_str[11:16] if len(arr_str) >= 16 else arr_str[:5]

            if not dep or not (time_from <= dep <= time_to):
                continue

            # Vérifier disponibilité TGV Max (prix 0 ou tag spécifique)
            is_max = False
            price = prop.get("price") or prop.get("minPrice") or seg.get("price") or {}
            if isinstance(price, dict):
                amount = price.get("amount") or price.get("value") or price.get("cents", -1)
                is_max = amount == 0
            elif isinstance(price, (int, float)):
                is_max = price == 0

            for fare in prop.get("fares") or prop.get("offers") or []:
                fare_code = str(fare.get("code") or fare.get("type") or "")
                if "MAX" in fare_code or "HAPPY" in fare_code:
                    is_max = True
                fp = fare.get("price") or fare.get("amount") or {}
                if isinstance(fp, dict) and fp.get("amount") == 0:
                    is_max = True
                elif isinstance(fp, (int, float)) and fp == 0:
                    is_max = True

            if is_max:
                trains.append({
                    "train_no": train_no,
                    "origin": origin,
                    "destination": destination,
                    "date": travel_date,
                    "departure": dep,
                    "arrival": arr,
                })

    return trains
