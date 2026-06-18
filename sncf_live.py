"""
Module de données temps réel SNCF Connect.

L'endpoint interne de SNCF Connect n'est pas documenté publiquement.
Pour l'identifier :
  1. Ouvrir https://www.sncf-connect.com dans Chrome
  2. DevTools → Onglet Réseau → filtre Fetch/XHR
  3. Lancer une recherche de billet (ex. Paris → Lyon, demain)
  4. Repérer la requête XHR vers l'API search (souvent /api/v1/trips ou similaire)
  5. Copier les headers (Authorization, x-api-key…) et le payload JSON
  6. Implémenter fetch_live() ci-dessous avec ces informations

En attendant, cette fonction retourne [] et l'application tourne
entièrement sur l'open data (check toutes les 30 min, suffisant).

TODO: implémenter fetch_live() une fois l'endpoint identifié.
"""
from typing import Dict, List


async def fetch_live(
    origin: str,
    destination: str,
    travel_date: str,
    time_from: str,
    time_to: str,
) -> List[Dict]:
    """
    TODO: récupérer les disponibilités en temps réel depuis SNCF Connect.
    Retourne [] tant que non implémenté — l'open data prend le relais.
    """
    return []
