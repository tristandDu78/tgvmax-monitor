"""
Scheduler APScheduler (AsyncIOScheduler) intégré au même event loop qu'uvicorn.

Tâches planifiées :
  • check_all_watches  — toutes les CHECK_INTERVAL_MINUTES minutes (défaut 30)
  • refresh_gares      — toutes les 24 h
"""
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from db import db
from discord_notif import send_dm
from sncf_live import fetch_live
from sncf_opendata import check_trains_opendata, refresh_gares_cache

INTERVAL = int(os.environ.get("CHECK_INTERVAL_MINUTES", "30"))
_scheduler = AsyncIOScheduler()


async def check_all_watches() -> None:
    print("[Scheduler] Démarrage du check…")
    watches = await db.get_active_watches()
    print(f"[Scheduler] {len(watches)} surveillance(s) active(s)")
    for watch in watches:
        try:
            await _check_one(watch)
        except Exception as exc:
            print(f"[Scheduler] Erreur surveillance {watch['id']} : {exc}")


async def _check_one(watch: dict) -> None:
    wid = watch["id"]
    origin = watch["origin"]
    dest = watch["destination"]
    travel_date = watch["travel_date"]
    time_from = watch["time_from"][:5]
    time_to = watch["time_to"][:5]
    discord_id = watch["discord_id"]

    # Live d'abord, open data en fallback
    trains = await fetch_live(origin, dest, travel_date, time_from, time_to)
    if not trains:
        trains = await check_trains_opendata(origin, dest, travel_date, time_from, time_to)

    # Mémoriser les trains trouvés pour l'affichage dans l'interface
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
            print(
                f"[Scheduler] ✅ Notifié {discord_id} : "
                f"train {train_no} {origin}→{dest} le {travel_date}"
            )


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
    _scheduler.start()
    print(f"[Scheduler] Démarré — intervalle : {INTERVAL} min")


def stop_scheduler() -> None:
    _scheduler.shutdown(wait=False)
