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

            # Aller d'abord sur sncf-connect.com pour initialiser les cookies
            print("[Playwright] Chargement initial de sncf-connect.com…")
            await page.goto("https://www.sncf-connect.com", wait_until="networkidle", timeout=40000)
            await asyncio.sleep(2)
            print(f"[Playwright] URL après chargement : {page.url}")

            # Aller sur la page Auth0 (Universal Login SPA)
            auth_url = (
                "https://auth.monidentifiant.sncf/authorize"
                "?response_type=code"
                "&client_id=mkEcrPWwH3EWhEvxBbZCjpHHVo6oJZlX"
                "&redirect_uri=https://www.sncf-connect.com/authenticate"
                "&scope=openid%20profile%20email"
                "&screen_hint=login"
                "&prompt=login"
            )
            print("[Playwright] Navigation vers Auth0 (Universal Login)…")
            await page.goto(auth_url, wait_until="networkidle", timeout=40000)
            await asyncio.sleep(3)
            print(f"[Playwright] URL Auth0 : {page.url}")

            # Auth0 redirige vers /u/login — attendre que l'URL change si encore sur /authorize
            if "/authorize" in page.url and "?" in page.url:
                print("[Playwright] En attente de la redirection Auth0…")
                try:
                    await page.wait_for_url("**/u/**", timeout=10000)
                    await asyncio.sleep(2)
                except Exception:
                    pass
                print(f"[Playwright] URL après attente : {page.url}")

            # Détecter si le formulaire est dans un iframe (Auth0 Universal Login)
            email_selector = 'input[type="email"], input[name="email"], input[name="username"]'
            print("[Playwright] Recherche du champ email (page + iframes)…")

            # Log des frames disponibles
            frames = page.frames
            print(f"[Playwright] Frames disponibles : {[f.url for f in frames]}")

            # Chercher dans la page principale d'abord
            target_frame = page
            try:
                await page.wait_for_selector(email_selector, timeout=5000)
                print("[Playwright] Email input trouvé dans la page principale")
            except Exception:
                # Chercher dans les iframes
                found_in_frame = False
                for frame in frames:
                    if frame == page.main_frame:
                        continue
                    try:
                        await frame.wait_for_selector(email_selector, timeout=3000)
                        target_frame = frame
                        found_in_frame = True
                        print(f"[Playwright] Email input trouvé dans iframe : {frame.url}")
                        break
                    except Exception:
                        pass

                if not found_in_frame:
                    # Debug : log HTML partiel et inputs de toutes les frames
                    for frame in frames:
                        try:
                            inputs = await frame.query_selector_all('input')
                            if inputs:
                                types = []
                                for inp in inputs:
                                    t = await inp.get_attribute('type')
                                    n = await inp.get_attribute('name')
                                    i = await inp.get_attribute('id')
                                    types.append(f"type={t} name={n} id={i}")
                                print(f"[Playwright] Frame {frame.url} inputs : {types}")
                        except Exception:
                            pass
                    body = await page.inner_text('body')
                    print(f"[Playwright] Body (500 chars) : {body[:500]}")
                    await browser.close()
                    return None

            await target_frame.fill(email_selector, SNCF_EMAIL)
            await asyncio.sleep(0.5)
            print("[Playwright] Email rempli")

            # Soumettre email
            try:
                await target_frame.click('button[type="submit"]', timeout=5000)
            except Exception:
                await target_frame.press(email_selector, "Enter")
            await asyncio.sleep(2)
            print(f"[Playwright] URL après email : {page.url}")

            # Attendre le champ mot de passe (même frame)
            print("[Playwright] Recherche du champ mot de passe…")
            pwd_selector = 'input[type="password"], input[name="password"]'
            try:
                await target_frame.wait_for_selector(pwd_selector, timeout=15000)
            except Exception:
                print(f"[Playwright] Mot de passe non trouvé. URL : {page.url}")
                await browser.close()
                return None

            await target_frame.fill(pwd_selector, SNCF_PASSWORD)
            await asyncio.sleep(0.5)
            print("[Playwright] Mot de passe rempli")

            # Soumettre
            try:
                await target_frame.click('button[type="submit"]', timeout=5000)
            except Exception:
                await target_frame.press(pwd_selector, "Enter")
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
