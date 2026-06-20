"""
Connexion automatique à SNCF Connect via Playwright (navigateur headless).
Récupère les cookies d'authentification pour le BFF API.
"""
import asyncio
import os
from typing import Optional

SNCF_EMAIL = os.environ.get("SNCF_EMAIL", "")
SNCF_PASSWORD = os.environ.get("SNCF_PASSWORD", "")


async def get_sncf_tokens() -> Optional[dict]:
    """
    Ouvre un navigateur headless, se connecte à SNCF Connect,
    et retourne les tokens d'accès extraits des cookies.
    """
    if not SNCF_EMAIL or not SNCF_PASSWORD:
        print("[Playwright] SNCF_EMAIL / SNCF_PASSWORD non configurés")
        return None

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[Playwright] Playwright non installé")
        return None

    print("[Playwright] Démarrage du navigateur…")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--disable-gpu",
                ],
            )
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/147.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
                locale="fr-FR",
            )

            # Masquer le flag webdriver
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
                Object.defineProperty(navigator, 'languages', { get: () => ['fr-FR', 'fr'] });
            """)

            page = await context.new_page()

            # Aller sur la page de connexion SNCF Connect
            print("[Playwright] Navigation vers sncf-connect.com…")
            await page.goto("https://www.sncf-connect.com", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            # Cliquer sur "Se connecter"
            try:
                await page.click('[data-testid="header-login-button"], a[href*="authenticate"], button:has-text("connecter")', timeout=10000)
                await asyncio.sleep(2)
            except Exception:
                # Aller directement sur la page de connexion
                await page.goto(
                    "https://www.sncf-connect.com/bff/api/v2/authenticate"
                    "?redirectUri=https://www.sncf-connect.com/authenticate"
                    "&screenHint=SIGN_IN&channel=web&market=fr_FR",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                await asyncio.sleep(2)

            # Attendre la page Auth0 et remplir email
            print("[Playwright] Remplissage du formulaire…")
            await page.wait_for_selector('input[type="email"], input[name="email"], #email', timeout=15000)
            await page.fill('input[type="email"], input[name="email"], #email', SNCF_EMAIL)
            await asyncio.sleep(0.5)

            # Chercher et cliquer le bouton "continuer" / "suivant"
            try:
                await page.click('button[type="submit"], button:has-text("Continuer"), button:has-text("Suivant")', timeout=5000)
                await asyncio.sleep(1)
            except Exception:
                await page.press('input[type="email"]', "Enter")
                await asyncio.sleep(1)

            # Remplir mot de passe
            await page.wait_for_selector('input[type="password"], input[name="password"], #password', timeout=10000)
            await page.fill('input[type="password"], input[name="password"], #password', SNCF_PASSWORD)
            await asyncio.sleep(0.5)

            # Soumettre
            await page.click('button[type="submit"], button:has-text("Se connecter"), button:has-text("Connexion")', timeout=5000)
            print("[Playwright] Attente de la redirection…")

            # Attendre le retour sur sncf-connect.com
            await page.wait_for_url("**/sncf-connect.com/**", timeout=20000)
            await asyncio.sleep(3)

            # Extraire les cookies
            cookies = await context.cookies()
            await browser.close()

            access_token = next(
                (c["value"] for c in cookies if c["name"] == "__Host-access-account-token"), None
            )
            id_token = next(
                (c["value"] for c in cookies if c["name"] == "__Host-id-account-token"), None
            )

            if not access_token:
                print("[Playwright] Token non trouvé dans les cookies")
                return None

            print("[Playwright] Tokens récupérés avec succès ✅")
            return {"access_token": access_token, "id_token": id_token or ""}

    except Exception as e:
        print(f"[Playwright] Erreur : {e}")
        return None
