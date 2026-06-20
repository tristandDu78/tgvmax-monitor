"""
Couche d'accès à la base de données Supabase via l'API REST PostgREST.
Toutes les méthodes sont async ; elles partagent les variables d'environnement
SUPABASE_URL et SUPABASE_KEY (clé service_role pour bypasser le RLS).
"""
import os
from datetime import date, datetime, timedelta
from typing import Optional

import httpx


class Database:
    def __init__(self) -> None:
        url = os.environ["SUPABASE_URL"].rstrip("/")
        key = os.environ["SUPABASE_KEY"]
        self.base = f"{url}/rest/v1"
        self._h = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------ users
    async def upsert_user(
        self,
        discord_id: str,
        username: str,
        avatar: Optional[str],
        access_token: str,
    ) -> None:
        headers = {**self._h, "Prefer": "resolution=merge-duplicates"}
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{self.base}/users",
                headers=headers,
                json={
                    "discord_id": discord_id,
                    "username": username,
                    "avatar": avatar,
                    "access_token": access_token,
                },
            )
            r.raise_for_status()

    # --------------------------------------------------------------- sessions
    async def get_session(self, token: str) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                f"{self.base}/sessions",
                headers=self._h,
                params={
                    "token": f"eq.{token}",
                    "select": "discord_id,users(username,avatar)",
                },
            )
            r.raise_for_status()
            data = r.json()
        if not data:
            return None
        s = data[0]
        return {
            "discord_id": s["discord_id"],
            "username": s["users"]["username"],
            "avatar": s["users"]["avatar"],
        }

    async def create_session(self, token: str, discord_id: str) -> None:
        expires = (datetime.utcnow() + timedelta(days=30)).isoformat() + "Z"
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{self.base}/sessions",
                headers=self._h,
                json={"token": token, "discord_id": discord_id, "expires_at": expires},
            )
            r.raise_for_status()

    async def delete_session(self, token: str) -> None:
        async with httpx.AsyncClient(timeout=15) as c:
            await c.delete(
                f"{self.base}/sessions",
                headers=self._h,
                params={"token": f"eq.{token}"},
            )

    # ---------------------------------------------------------------- watches
    async def get_watches(self, discord_id: str) -> list:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                f"{self.base}/watches",
                headers=self._h,
                params={
                    "discord_id": f"eq.{discord_id}",
                    "active": "eq.true",
                    "order": "created_at.desc",
                },
            )
            r.raise_for_status()
            return r.json() or []

    async def create_watch(
        self,
        discord_id: str,
        origin: str,
        destination: str,
        travel_date: str,
        time_from: str,
        time_to: str,
    ) -> str:
        headers = {**self._h, "Prefer": "return=representation"}
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{self.base}/watches",
                headers=headers,
                json={
                    "discord_id": discord_id,
                    "origin": origin,
                    "destination": destination,
                    "travel_date": travel_date,
                    "time_from": time_from,
                    "time_to": time_to,
                },
            )
            r.raise_for_status()
            return r.json()[0]["id"]

    async def delete_watch(self, watch_id: str, discord_id: str) -> None:
        async with httpx.AsyncClient(timeout=15) as c:
            await c.delete(
                f"{self.base}/watches",
                headers=self._h,
                params={"id": f"eq.{watch_id}", "discord_id": f"eq.{discord_id}"},
            )

    async def get_active_watches(self) -> list:
        today = date.today().isoformat()
        async with httpx.AsyncClient(timeout=15) as c:
            # Désactiver les surveillances passées
            await c.patch(
                f"{self.base}/watches",
                headers=self._h,
                params={"travel_date": f"lt.{today}", "active": "eq.true"},
                json={"active": False},
            )
            r = await c.get(
                f"{self.base}/watches",
                headers=self._h,
                params={"active": "eq.true", "travel_date": f"gte.{today}"},
            )
            r.raise_for_status()
            return r.json() or []

    async def update_watch_trains(self, watch_id: str, trains: list) -> None:
        async with httpx.AsyncClient(timeout=15) as c:
            await c.patch(
                f"{self.base}/watches",
                headers=self._h,
                params={"id": f"eq.{watch_id}"},
                json={"last_check_trains": trains},
            )

    # -------------------------------------------------------- notified_trains
    async def is_train_notified(
        self, watch_id: str, train_no: str, travel_date: str
    ) -> bool:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                f"{self.base}/notified_trains",
                headers=self._h,
                params={
                    "watch_id": f"eq.{watch_id}",
                    "train_no": f"eq.{train_no}",
                    "travel_date": f"eq.{travel_date}",
                },
            )
            r.raise_for_status()
            return bool(r.json())

    async def mark_train_notified(
        self, watch_id: str, train_no: str, travel_date: str
    ) -> None:
        headers = {**self._h, "Prefer": "resolution=ignore-duplicates"}
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{self.base}/notified_trains",
                headers=headers,
                json={
                    "watch_id": watch_id,
                    "train_no": train_no,
                    "travel_date": travel_date,
                },
            )
            r.raise_for_status()


    # --------------------------------------------------------- sncf_accounts
    async def get_sncf_account(self, discord_id: str) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                f"{self.base}/sncf_accounts",
                headers=self._h,
                params={"discord_id": f"eq.{discord_id}"},
            )
            r.raise_for_status()
            data = r.json()
        return data[0] if data else None

    async def upsert_sncf_account(self, discord_id: str, id_token: str = "", **fields) -> None:
        fields["id_token"] = id_token
        headers = {**self._h, "Prefer": "resolution=merge-duplicates"}
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{self.base}/sncf_accounts",
                headers=headers,
                json={"discord_id": discord_id, **fields},
            )
            r.raise_for_status()

    async def update_sncf_tokens(
        self,
        discord_id: str,
        access_token: str,
        refresh_token: Optional[str],
        token_expires_at: str,
    ) -> None:
        payload: dict = {"access_token": access_token, "token_expires_at": token_expires_at}
        if refresh_token is not None:
            payload["refresh_token"] = refresh_token
        async with httpx.AsyncClient(timeout=15) as c:
            await c.patch(
                f"{self.base}/sncf_accounts",
                headers=self._h,
                params={"discord_id": f"eq.{discord_id}"},
                json=payload,
            )

    async def delete_sncf_account(self, discord_id: str) -> None:
        async with httpx.AsyncClient(timeout=15) as c:
            await c.delete(
                f"{self.base}/sncf_accounts",
                headers=self._h,
                params={"discord_id": f"eq.{discord_id}"},
            )

    async def get_sncf_accounts_expiring_soon(self) -> list:
        """Retourne les comptes dont le refresh token expire dans moins de 5 jours."""
        in_5_days = (datetime.utcnow() + timedelta(days=5)).isoformat() + "Z"
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                f"{self.base}/sncf_accounts",
                headers=self._h,
                params={"refresh_expires_at": f"lt.{in_5_days}"},
            )
            r.raise_for_status()
            return r.json() or []


db = Database()
