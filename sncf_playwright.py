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
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
                locale="fr-FR",
            )

            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
                Object.defineProperty(navigator, 'languages', { get: () => ['fr-FR', 'fr'] });
            """)

            page = await context.new_page()

            # Aller directement sur la page Auth0 de SNCF Connect
            auth_url = (
                "https://auth.monidentifiant.sncf/authorize"
                "?response_type=code"
                "&client_id=mkEcrPWwH3EWhEvxBbZCjpHHVo6oJZlX"
                "&redirect_uri=https://www.sncf-connect.com/authenticate"
                "&scope=openid profile email"
                "&screen_hint=login"
            )
            print(f"[Playwright] Navigation vers Auth0…")
            await page.goto(auth_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            print(f"[Playwright] URL actuelle : {page.url}")

            # Attendre l'input email (avec fallback sur tous les inputs)
            print("[Playwright] Recherche du champ email…")
            try:
                await page.wait_for_selector('input[type="email"], input[name="email"], input[name="username"], #email, #username', timeout=20000)
            except Exception:
                # Logger les inputs visibles pour debug
                inputs = await page.query_selector_all('input')
                types = []
                for inp in inputs:
                    t = await inp.get_attribute('type')
                    n = await inp.get_attribute('name')
                    types.append(f"type={t} name={n}")
                print(f"[Playwright] Inputs trouvés : {types}")
                print(f"[Playwright] URL : {page.url}")
                await browser.close()
                return None

            await page.fill('input[type="email"], input[name="email"], input[name="username"], #email, #username', SNCF_EMAIL)
            await asyncio.sleep(0.5)
            print("[Playwright] Email rempli")

            # Soumettre email
            try:
                await page.click('button[type="submit"]', timeout=5000)
            except Exception:
                await page.keyboard.press("Enter")
            await asyncio.sleep(2)
            print(f"[Playwright] URL après email : {page.url}")

            # Attendre le champ mot de passe
            print("[Playwright] Recherche du champ mot de passe…")
            try:
                await page.wait_for_selector('input[type="password"], input[name="password"], #password', timeout=15000)
            except Exception:
                inputs = await page.query_selector_all('input')
                types = []
                for inp in inputs:
                    t = await inp.get_attribute('type')
                    n = await inp.get_attribute('name')
                    types.append(f"type={t} name={n}")
                print(f"[Playwright] Inputs trouvés : {types}")
                print(f"[Playwright] URL : {page.url}")
                await browser.close()
                return None

            await page.fill('input[type="password"], input[name="password"], #password', SNCF_PASSWORD)
            await asyncio.sleep(0.5)
            print("[Playwright] Mot de passe rempli")

            # Soumettre
            try:
                await page.click('button[type="submit"]', timeout=5000)
            except Exception:
                await page.keyboard.press("Enter")
            print("[Playwright] Attente de la redirection…")

            # Attendre le retour sur sncf-connect.com
            try:
                await page.wait_for_url("*sncf-connect.com*", timeout=25000)
            except Exception:
                print(f"[Playwright] Timeout redirection, URL actuelle : {page.url}")
                await browser.close()
                return None

            await asyncio.sleep(3)
            print(f"[Playwright] URL finale : {page.url}")

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
                all_names = [c["name"] for c in cookies if "sncf" in c.get("domain", "")]
                print(f"[Playwright] Token non trouvé. Cookies SNCF disponibles : {all_names}")
                return None

            print("[Playwright] Tokens récupérés avec succès ✅")
            return {"access_token": access_token, "id_token": id_token or ""}

    except Exception as e:
        print(f"[Playwright] Erreur : {e}")
        return None
