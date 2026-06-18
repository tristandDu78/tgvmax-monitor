"""
Bot Discord minimal pour l'envoi de messages privés.
Tourne dans le même processus asyncio que FastAPI (démarré via lifespan).
"""
import os

import discord
from discord.ext import commands

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready() -> None:
    print(f"[Discord] Bot connecté : {bot.user} (id={bot.user.id})")


async def send_dm(discord_id: str, message: str) -> bool:
    """
    Envoie un DM à un utilisateur Discord.
    Retourne True si réussi, False sinon (DMs désactivés, utilisateur introuvable…).
    """
    await bot.wait_until_ready()
    try:
        user = await bot.fetch_user(int(discord_id))
        await user.send(message)
        return True
    except discord.Forbidden:
        print(
            f"[Discord] DM refusé pour {discord_id} "
            "(l'utilisateur a peut-être désactivé les DMs des membres du serveur)"
        )
        return False
    except discord.NotFound:
        print(f"[Discord] Utilisateur introuvable : {discord_id}")
        return False
    except Exception as exc:
        print(f"[Discord] Erreur DM vers {discord_id} : {exc}")
        return False
