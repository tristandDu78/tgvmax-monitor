"""
Scheduler APScheduler (AsyncIOScheduler) intégré au même event loop qu'uvicorn.
"""
import os
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from db import db
from discord_notif import send_dm
from sncf_auth import refresh_access_token, login_with_tokens
from sncf_live import fetch_live
from sncf_opendata import check_trains_opendata, refresh_gares_cache

INTERVAL = int(os.environ.get("CHECK_INTERVAL_MINUTES", "30"))
SNCF_OWNER_ID = os.environ.get("SNCF_OWNER_DISCORD_ID", "")
_scheduler = AsyncIOScheduler()
_last_check: str | None = None


def get_scheduler_info() -> dict:
    job = _scheduler.get_job("check_watches")
    next_run = job.next_run_time.isoformat() if job and job.next_run_time else None
    return {"last_check": _last_check, "next_check": next_run}


async def check_all_watches() -> None:
    global _last_check
    _last_check = datetime.now(timezone.utc).isoformat()
    print("[Scheduler] Démarrage du check…")
    watches = await db.get_active_watches()
    print(f"[Scheduler] {len(watches)} surveillance(s) active(s)")
    for watch in watches:
        try:
            await _check_one(watch)
        except Exception as exc:
            print(f"[Scheduler] Erreur surveillance {watch['id']} : {exc}")


async def _get_fresh_sncf_account(discord_id: str) -> dict | None:
    """Retourne le compte SNCF avec token valide, refresh si nécessaire."""
    account = await db.get_sncf_account(discord_id)
    if not account:
        return None

    expires_at = datetime.fromisoformat(account["token_expires_at"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)

    if expires_at - now < timedelta(minutes=5):
        try:
            new_tokens = await refresh_access_token(account["refresh_token"])
            await db.update_sncf_tokens(
                discord_id,
                new_tokens["access_token"],
                new_tokens["refresh_token"],
                new_tokens["token_expires_at"],
            )
            account.update(new_tokens)
            print(f"[Scheduler] Token SNCF rafraîchi pour {discord_id}")
        except Exception as e:
            print(f"[Scheduler] Refresh token SNCF échoué pour {discord_id}: {e}")
            return None

    return account


async def _check_one(watch: dict) -> None:
    wid = watch["id"]
    origin = watch["origin"]
    dest = watch["destination"]
    travel_date = watch["travel_date"]
    time_from = watch["time_from"][:5]
    time_to = watch["time_to"][:5]
    discord_id = watch["discord_id"]

    print(f"[Scheduler] Check: {origin}→{dest} le {travel_date} {time_from}-{time_to}")

    # Toujours utiliser le compte SNCF du propriétaire de l'app
    sncf_owner = SNCF_OWNER_ID or discord_id
    sncf_account = await _get_fresh_sncf_account(sncf_owner)
    trains = []

    if sncf_account:
        trains = await fetch_live(origin, dest, travel_date, time_from, time_to, sncf_account)
        print(f"[Scheduler] Live: {len(trains)} train(s)")

    if not trains:
        trains = await check_trains_opendata(origin, dest, travel_date, time_from, time_to)
        print(f"[Scheduler] OpenData: {len(trains)} train(s)")

    await db.update_watch_trains(wid, trains)

    for train in trains:
        train_no = train["train_no"]
        if await db.is_train_notified(wid, train_no, travel_date):
            continue

        msg = (
            f"🚄 **Place TGV Max disponible !**\n\n"
            f"**{origin}** → **{dest}**\n"
            f"📅 {travel_date}\n"
            f"🕐 Départ **{train['departure']}** → Arrivée **{train['arrival']}**\n"
            f"🚆 Train n° **{train_no}**\n\n"
            f"👉 Réservez vite sur [SNCF Connect](https://www.sncf-connect.com) !"
        )
        ok = await send_dm(discord_id, msg)
        if ok:
            await db.mark_train_notified(wid, train_no, travel_date)
            print(f"[Scheduler] ✅ Notifié {discord_id} : train {train_no} {origin}→{dest} le {travel_date}")


async def refresh_sncf_tokens_playwright() -> None:
    """Renouvelle les tokens SNCF du propriétaire via Playwright."""
    if not SNCF_OWNER_ID:
        return
    try:
        from sncf_playwright import get_sncf_tokens
        tokens = await get_sncf_tokens()
        if not tokens or not tokens.get("access_token"):
            print("[Scheduler] Playwright : aucun token récupéré")
            return
        result = await login_with_tokens(tokens["access_token"], tokens.get("id_token", ""))
        await db.upsert_sncf_account(
            discord_id=SNCF_OWNER_ID,
            access_token=result["access_token"],
            id_token=result.get("id_token", ""),
            refresh_token=None,
            token_expires_at=result["token_expires_at"],
            refresh_expires_at=result["refresh_expires_at"],
            customer_id=result.get("customer_id"),
            card_number=result.get("card_number"),
            card_label=result.get("card_label"),
            date_of_birth=result.get("date_of_birth"),
            first_name=result.get("first_name"),
            last_name=result.get("last_name"),
            initials=result.get("initials"),
        )
        print("[Scheduler] Tokens SNCF rafraîchis via Playwright ✅")
    except Exception as e:
        print(f"[Scheduler] Playwright refresh échoué : {e}")


async def check_expiring_sncf_tokens() -> None:
    """Notifie les utilisateurs dont le refresh token expire dans moins de 5 jours."""
    expiring = await db.get_sncf_accounts_expiring_soon()
    for account in expiring:
        discord_id = account["discord_id"]
        msg = (
            "⚠️ **Reconnexion SNCF requise**\n\n"
            "Votre connexion SNCF Connect va expirer dans moins de 5 jours.\n"
            "Rendez-vous sur l'application pour vous reconnecter et continuer à "
            "recevoir les alertes TGV Max en temps réel.\n\n"
            "👉 https://tgvmax-monitor.onrender.com"
        )
        await send_dm(discord_id, msg)
        print(f"[Scheduler] Notif expiration SNCF envoyée à {discord_id}")


def start_scheduler() -> None:
    _scheduler.add_job(
        check_all_watches,
        trigger=IntervalTrigger(minutes=INTERVAL),
        id="check_watches",
        replace_existing=True,
        misfire_grace_time=60,
    )
    _scheduler.add_job(
        refresh_gares_cache,
        trigger=IntervalTrigger(hours=24),
        id="refresh_gares",
        replace_existing=True,
    )
    _scheduler.add_job(
        check_expiring_sncf_tokens,
        trigger=IntervalTrigger(hours=24),
        id="check_sncf_expiry",
        replace_existing=True,
    )
    if SNCF_OWNER_ID:
        _scheduler.add_job(
            refresh_sncf_tokens_playwright,
            trigger=IntervalTrigger(minutes=25),
            id="refresh_sncf_playwright",
            replace_existing=True,
        )
        print("[Scheduler] Refresh Playwright SNCF activé (toutes les 25 min)")
    _scheduler.start()
    print(f"[Scheduler] Démarré — intervalle : {INTERVAL} min")


def stop_scheduler() -> None:
    _scheduler.shutdown(wait=False)
