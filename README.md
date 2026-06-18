# 🚄 TGV Max Monitor

Recevez un **message privé Discord** dès qu'une place TGV Max (MAX Jeune) est disponible
sur le trajet de votre choix. Aucune connaissance technique requise pour l'utiliser.

---

## Comment ça marche

1. Vous vous connectez avec votre compte Discord sur l'application web.
2. Vous renseignez un trajet (gare de départ, gare d'arrivée, date, créneau horaire).
3. L'application vérifie toutes les 30 minutes si une place Max est disponible sur ce train.
4. Dès qu'une place est trouvée, vous recevez un **DM Discord** avec le numéro de train
   et les horaires. Vous n'avez plus qu'à réserver sur SNCF Connect.

---

## Déploiement pas-à-pas (pour débutants)

Suivez ces 5 étapes dans l'ordre. Comptez 30 à 45 minutes au total.

---

### Étape 1 — Créer l'application Discord et le bot

1. Rendez-vous sur [discord.com/developers/applications](https://discord.com/developers/applications)
   et connectez-vous avec votre compte Discord.

2. Cliquez sur **"New Application"** (bouton bleu en haut à droite).
   - Donnez-lui un nom, par exemple `TGV Max Monitor`.
   - Acceptez les CGU, puis cliquez sur **"Create"**.

3. Dans le menu de gauche, cliquez sur **"OAuth2"**.
   - Notez l'**"Application ID"** — c'est votre `DISCORD_CLIENT_ID`.
   - Cliquez sur **"Reset Secret"**, confirmez, puis copiez le secret affiché.
     C'est votre `DISCORD_CLIENT_SECRET`. **Sauvegardez-le maintenant, il ne s'affichera plus.**

4. Dans le menu de gauche, cliquez sur **"Bot"**.
   - Cliquez sur **"Add Bot"**, puis confirmez.
   - Cliquez sur **"Reset Token"**, confirmez, copiez le token.
     C'est votre `DISCORD_BOT_TOKEN`. **Sauvegardez-le maintenant.**
   - Dans la section **"Privileged Gateway Intents"**, aucun intent n'est nécessaire.
     Laissez tout désactivé.

---

### Étape 2 — Créer le serveur Discord de notification et inviter le bot

Le bot a besoin d'un serveur Discord pour pouvoir envoyer des DM aux utilisateurs.
Vous pouvez créer un serveur dédié ou utiliser un serveur existant dont vous êtes propriétaire.

#### 2a. Créer le serveur de notification

1. Dans Discord (application ou web), cliquez sur le **"+"** dans la barre de gauche.
2. Choisissez **"Créer le mien"** → **"Pour mes amis et moi"**.
3. Donnez-lui un nom, par exemple `TGV Max Notifications`. Cliquez sur **"Créer"**.

#### 2b. Récupérer l'ID du serveur

1. Dans Discord, allez dans **Paramètres utilisateur** > **Avancé** >
   activez **"Mode développeur"**.
2. Revenez sur votre serveur de notification, faites un **clic droit** sur le nom du serveur
   en haut à gauche, et choisissez **"Copier l'identifiant du serveur"**.
   C'est votre `DISCORD_GUILD_ID`.

#### 2c. Inviter le bot sur le serveur

1. Retournez sur le portail développeur Discord, dans votre application.
2. Menu de gauche → **"OAuth2"** → **"URL Generator"**.
3. Dans **"Scopes"**, cochez : `bot`.
4. Dans **"Bot Permissions"**, cochez : `Send Messages` (sous "Text Permissions").
5. Copiez l'URL générée en bas de page, ouvrez-la dans votre navigateur.
6. Sélectionnez votre serveur de notification et cliquez sur **"Autoriser"**.

Le bot est maintenant membre du serveur. ✅

#### 2d. Configurer l'URL de redirection OAuth2

1. Dans le portail développeur, menu **"OAuth2"**.
2. Dans la section **"Redirects"**, cliquez sur **"Add Redirect"**.
3. Entrez l'URL suivante (vous remplacerez `<votre-app>` après le déploiement Render) :
   ```
   https://<votre-app>.onrender.com/auth/callback
   ```
   Pour l'instant, notez-la sur le côté, vous la renseignerez après l'étape 4.

---

### Étape 3 — Créer la base de données Supabase

1. Créez un compte gratuit sur [supabase.com](https://supabase.com) (via GitHub ou email).

2. Cliquez sur **"New project"**.
   - Choisissez un nom, un mot de passe (notez-le), et la région **"West EU (Ireland)"**
     pour de meilleures performances. Cliquez sur **"Create new project"**.
   - Attendez 1-2 minutes que le projet se crée.

3. Dans le menu de gauche, cliquez sur **"Project Settings"** (icône engrenage), puis **"API"**.
   - Notez l'**URL du projet** (ex: `https://abcdef.supabase.co`) → `SUPABASE_URL`
   - Dans la section **"Project API keys"**, copiez la clé **`service_role`** (pas `anon`) → `SUPABASE_KEY`
   > ⚠️ La clé `service_role` donne un accès total à votre base. Ne la partagez jamais.

4. Dans le menu de gauche, cliquez sur **"SQL Editor"**.
   Cliquez sur **"New query"**, collez le SQL suivant et cliquez sur **"Run"** :

```sql
-- Utilisateurs connectés via Discord
CREATE TABLE users (
    discord_id  TEXT PRIMARY KEY,
    username    TEXT NOT NULL,
    avatar      TEXT,
    access_token TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Sessions de connexion web
CREATE TABLE sessions (
    token       TEXT PRIMARY KEY,
    discord_id  TEXT NOT NULL REFERENCES users(discord_id) ON DELETE CASCADE,
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Surveillances de trajets
CREATE TABLE watches (
    id                UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    discord_id        TEXT NOT NULL REFERENCES users(discord_id) ON DELETE CASCADE,
    origin            TEXT NOT NULL,
    destination       TEXT NOT NULL,
    travel_date       DATE NOT NULL,
    time_from         TEXT NOT NULL,
    time_to           TEXT NOT NULL,
    active            BOOLEAN DEFAULT TRUE NOT NULL,
    last_check_trains JSONB DEFAULT '[]'::JSONB NOT NULL,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- Trains déjà notifiés (évite les doublons de DM)
CREATE TABLE notified_trains (
    watch_id    UUID NOT NULL REFERENCES watches(id) ON DELETE CASCADE,
    train_no    TEXT NOT NULL,
    travel_date DATE NOT NULL,
    notified_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (watch_id, train_no, travel_date)
);
```

Vous devriez voir **"Success. No rows returned"**. ✅

---

### Étape 4 — Déployer sur Render

1. Créez un compte gratuit sur [render.com](https://render.com) (via GitHub ou email).

2. Mettez votre code sur GitHub :
   - Créez un compte gratuit sur [github.com](https://github.com) si vous n'en avez pas.
   - Cliquez sur **"New repository"** (bouton vert), donnez un nom (`tgvmax-monitor`), laissez tout par défaut, cliquez **"Create repository"**.
   - Sur la page du dépôt vide, cliquez **"uploading an existing file"**.
   - Glissez-déposez **tous les fichiers du dossier** `tgvmax-monitor/` (y compris le sous-dossier `static/`).
   - Cliquez **"Commit changes"**. Votre code est en ligne.

3. Sur Render, cliquez sur **"New +"** → **"Web Service"**.
   - Connectez votre compte GitHub si ce n'est pas déjà fait.
   - Sélectionnez le dépôt `tgvmax-monitor`.
   - Render détecte automatiquement `render.yaml`. Cliquez sur **"Apply"**.

4. Avant de déployer, renseignez les **variables d'environnement** (section "Environment") :

   | Clé | Valeur |
   |-----|--------|
   | `DISCORD_CLIENT_ID` | Votre Application ID Discord |
   | `DISCORD_CLIENT_SECRET` | Votre secret OAuth2 Discord |
   | `DISCORD_BOT_TOKEN` | Votre token bot Discord |
   | `DISCORD_GUILD_ID` | L'ID de votre serveur de notification |
   | `SUPABASE_URL` | L'URL de votre projet Supabase |
   | `SUPABASE_KEY` | La clé `service_role` Supabase |
   | `APP_URL` | `https://<nom-service>.onrender.com` |
   | `CHECK_INTERVAL_MINUTES` | `30` |

   > L'URL Render est de la forme `https://tgvmax-monitor-xxxx.onrender.com`.
   > Vous la verrez en haut de la page du service une fois déployé.

5. Cliquez sur **"Create Web Service"**. Le déploiement prend 3-5 minutes.

6. Une fois déployé, **revenez dans le portail Discord** (étape 2d) et ajoutez l'URL de redirection :
   ```
   https://<votre-url-render>/auth/callback
   ```

---

### Étape 5 — Configurer UptimeRobot (keepalive)

Le free tier Render met le service en veille après 15 minutes d'inactivité.
UptimeRobot le réveille en le pingant toutes les 5 minutes.

1. Créez un compte gratuit sur [uptimerobot.com](https://uptimerobot.com).
2. Cliquez sur **"Add New Monitor"**.
   - Type : **HTTP(s)**
   - Friendly Name : `TGV Max Monitor`
   - URL : `https://<votre-url-render>/health`
   - Monitoring Interval : **5 minutes**
3. Cliquez sur **"Create Monitor"**. ✅

---

## Votre application est en ligne ! 🎉

Ouvrez `https://<votre-url-render>` dans votre navigateur, connectez-vous avec Discord,
et créez votre première surveillance de trajet.

---

## Notes importantes

- **Réservation** : L'application vous signale uniquement la disponibilité.
  La réservation se fait manuellement sur [SNCF Connect](https://www.sncf-connect.com).

- **DMs Discord** : Pour recevoir les messages privés, assurez-vous que dans Discord,
  vous autorisez les DMs des membres du serveur de notification :
  Paramètres Discord → Confidentialité et sécurité → "Autoriser les messages privés
  des membres du serveur" doit être activé pour ce serveur.

- **Données personnelles** : Seuls votre identifiant Discord et vos critères de trajet
  sont stockés. Aucun identifiant SNCF ni donnée bancaire n'est utilisé.

- **Fréquence** : La vérification a lieu toutes les 30 minutes pour rester dans des
  limites d'utilisation raisonnables de l'API SNCF.

---

## Développement local

```bash
# Créer un environnement virtuel
python -m venv venv
source venv/bin/activate   # Linux/Mac
venv\Scripts\activate      # Windows

# Installer les dépendances
pip install -r requirements.txt

# Copier et remplir le fichier .env
cp .env.example .env
# (éditez .env avec vos valeurs)

# Charger les variables et lancer
# Linux/Mac :
export $(cat .env | xargs) && uvicorn main:app --reload
# Windows PowerShell :
Get-Content .env | ForEach-Object { $k,$v = $_ -split '=',2; [System.Environment]::SetEnvironmentVariable($k,$v) }
uvicorn main:app --reload
```

L'application sera accessible sur `http://localhost:8000`.
Pensez à ajouter `http://localhost:8000/auth/callback` dans les redirects Discord.

---

## Structure du projet

```
tgvmax-monitor/
├── main.py             FastAPI + OAuth2 Discord + routes API
├── db.py               Accès Supabase (REST PostgREST)
├── sncf_opendata.py    Données SNCF open data (tgvmax dataset)
├── sncf_live.py        Stub données temps réel (TODO)
├── discord_notif.py    Bot Discord (envoi de DMs)
├── scheduler.py        Vérifications périodiques (APScheduler)
├── index.html          Interface web (CSS et JS intégrés, un seul fichier)
├── static/
│   ├── style.css       Styles (utilisé en production)
│   └── app.js          Logique frontend (utilisé en production)
├── preview_server.py   Serveur de test local (pas pour la prod)
├── requirements.txt
├── render.yaml         Config déploiement Render
├── .env.example        Exemple de variables d'environnement
└── README.md
```
