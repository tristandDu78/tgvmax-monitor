"""
Point d'entrée de l'application.
FastAPI + bot Discord tournent dans le même processus asyncio.

Flux OAuth2 Discord :
  /auth/login  →  Discord  →  /auth/callback  →  /
"""
import asyncio
import os
import secrets
from contextlib import asynccontextmanager
from datetime import date, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from db import db
from discord_notif import bot, send_dm
from scheduler import get_scheduler_info, start_scheduler, stop_scheduler
from sncf_opendata import get_gares, refresh_gares_cache

# ----------------------------------------------------------------- config
CLIENT_ID = os.environ["DISCORD_CLIENT_ID"]
CLIENT_SECRET = os.environ["DISCORD_CLIENT_SECRET"]
BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
GUILD_ID = os.environ["DISCORD_GUILD_ID"]
APP_URL = os.environ.get(
    "APP_URL",
    os.environ.get("RENDER_EXTERNAL_URL", "http://localhost:8000"),
).rstrip("/")

REDIRECT_URI = f"{APP_URL}/auth/callback"
DISCORD_API = "https://discord.com/api/v10"


# --------------------------------------------------------------- lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(bot.start(BOT_TOKEN))
    await refresh_gares_cache()
    start_scheduler()
    yield
    stop_scheduler()
    await bot.close()


app = FastAPI(title="TGV Max Monitor", lifespan=lifespan)


# ----------------------------------------------------------------- helpers
def _oauth_url(state: str) -> str:
    params = urlencode(
        {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": "identify guilds.join",
            "state": state,
        }
    )
    return f"https://discord.com/api/oauth2/authorize?{params}"


async def _current_user(request: Request) -> dict | None:
    token = request.cookies.get("session")
    if not token:
        return None
    return await db.get_session(token)


# ------------------------------------------------------------------ routes
@app.get("/", response_class=HTMLResponse)
async def index():
    with open("index.html", encoding="utf-8") as f:
        return f.read()


@app.get("/health")
async def health():
    """Endpoint pour UptimeRobot (keepalive du free tier Render)."""
    return {"status": "ok"}


# ---------------------------------------------------------- OAuth2 Discord
@app.get("/auth/login")
async def login(request: Request):
    state = secrets.token_urlsafe(16)
    response = RedirectResponse(_oauth_url(state))
    response.set_cookie("oauth_state", state, max_age=300, httponly=True, samesite="lax")
    return response


@app.get("/auth/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if error:
        return RedirectResponse("/?error=access_denied")

    stored = request.cookies.get("oauth_state")
    if not state or state != stored:
        return RedirectResponse("/?error=invalid_state")

    async with httpx.AsyncClient(timeout=15) as c:
        # Échange du code contre un access token
        token_r = await c.post(
            f"{DISCORD_API}/oauth2/token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_r.status_code != 200:
            return RedirectResponse("/?error=token_exchange_failed")
        token_data = token_r.json()
        access_token = token_data["access_token"]

        # Récupération du profil Discord
        user_r = await c.get(
            f"{DISCORD_API}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_r.raise_for_status()
        user = user_r.json()

        # Ajout automatique au serveur Discord de notification
        await c.put(
            f"{DISCORD_API}/guilds/{GUILD_ID}/members/{user['id']}",
            headers={"Authorization": f"Bot {BOT_TOKEN}"},
            json={"access_token": access_token},
        )

    await db.upsert_user(
        discord_id=user["id"],
        username=user.get("global_name") or user["username"],
        avatar=user.get("avatar"),
        access_token=access_token,
    )

    session_token = secrets.token_urlsafe(32)
    await db.create_session(session_token, user["id"])

    response = RedirectResponse("/")
    response.set_cookie(
        "session", session_token, max_age=30 * 86400, httponly=True, samesite="lax"
    )
    response.delete_cookie("oauth_state")
    return response


@app.get("/auth/logout")
async def logout(request: Request):
    token = request.cookies.get("session")
    if token:
        await db.delete_session(token)
    response = RedirectResponse("/")
    response.delete_cookie("session")
    return response


# ---------------------------------------------------------------- API JSON
@app.get("/api/me")
async def me(request: Request):
    user = await _current_user(request)
    if not user:
        return JSONResponse({"authenticated": False})
    return JSONResponse({"authenticated": True, "user": user})


@app.get("/api/gares")
async def gares(q: str = ""):
    return JSONResponse(await get_gares(q))


@app.get("/api/watches")
async def list_watches(request: Request):
    user = await _current_user(request)
    if not user:
        raise HTTPException(401, "Non connecté")
    return JSONResponse(await db.get_watches(user["discord_id"]))


@app.post("/api/watches")
async def add_watch(request: Request):
    user = await _current_user(request)
    if not user:
        raise HTTPException(401, "Non connecté")

    data = await request.json()
    required = ["origin", "destination", "travel_date", "time_from", "time_to"]
    for field in required:
        if not data.get(field):
            raise HTTPException(400, f"Champ manquant : {field}")

    # Validation de la date (max 30 jours)
    try:
        travel = date.fromisoformat(data["travel_date"])
    except ValueError:
        raise HTTPException(400, "Format de date invalide")
    today = date.today()
    if travel < today or travel > today + timedelta(days=30):
        raise HTTPException(400, "La date doit être dans les 30 prochains jours")

    watch_id = await db.create_watch(
        discord_id=user["discord_id"],
        origin=data["origin"],
        destination=data["destination"],
        travel_date=data["travel_date"],
        time_from=data["time_from"],
        time_to=data["time_to"],
    )
    return JSONResponse({"id": watch_id}, status_code=201)


@app.get("/api/scheduler")
async def scheduler_info():
    return JSONResponse(get_scheduler_info())


@app.delete("/api/watches/{watch_id}")
async def delete_watch(watch_id: str, request: Request):
    user = await _current_user(request)
    if not user:
        raise HTTPException(401, "Non connecté")
    await db.delete_watch(watch_id, user["discord_id"])
    return JSONResponse({"ok": True})
