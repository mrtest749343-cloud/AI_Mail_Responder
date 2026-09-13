# Documentation — AI Email Responder

Cette documentation complète le `README.md` : elle détaille la carte du
projet, l'installation locale pas à pas, le déploiement sur Vercel, et les
mesures de protection du site.

---

## 1. Carte du projet

```text
ai-email-responder/
├── app.py                  # Application Flask : routes pages + API REST
├── email_processor.py      # Connexion IMAP/SMTP, lecture et envoi des mails
├── answer_matcher.py       # Sélection du meilleur modèle par mots-clés
├── answer_adapter.py       # Remplissage des {placeholders} + polish IA optionnel
├── utils.py                # Lecture/écriture JSON, hachage mot de passe,
│                            # décorateur login_required, anti brute-force
├── init_db.py               # Génère data/data.json avec le mot de passe haché
├── requirements.txt         # Dépendances Python
├── vercel.json               # Configuration de déploiement serverless
├── .env.example               # Modèle des variables d'environnement
├── .gitignore
├── README.md                   # Vue d'ensemble et démarrage rapide
├── Documentation.md              # Ce document
├── data/
│   └── data.json              # Compte admin (haché), clé API, base de réponses
│                                # — généré par init_db.py, jamais commité
├── static/
│   ├── css/style.css            # Thème "registre postal"
│   └── js/main.js                # Appels AJAX vers /api/*
└── templates/
    ├── base.html                  # Squelette commun (en-tête, polices, styles)
    ├── welcome.html                 # Page publique, aucune donnée utilisateur
    ├── login.html                     # Formulaire de connexion
    └── dashboard.html                   # Courrier entrant + base de réponses
```

### Flux de traitement d'un e-mail

1. `email_processor.fetch_unread()` récupère les messages non lus par IMAP.
2. `answer_matcher.get_best_template(body)` note chaque entrée de la base
   selon le nombre de mots-clés trouvés dans le message, et retient la
   meilleure (ou un modèle de secours si aucune ne correspond).
3. `answer_adapter.adapt_template(...)` remplace les `{placeholders}` du
   modèle par des valeurs extraites du message (nom de l'expéditeur, numéro
   de commande...), puis — si une clé d'API est renseignée — envoie le texte
   à un modèle de langage pour un polissage de forme, sans changer les faits.
4. `email_processor.send_reply(...)` envoie la réponse par SMTP en la
   rattachant au fil d'origine (`In-Reply-To`, `References`).
5. Le message est marqué comme lu pour ne pas être retraité.

---

## 2. Installation locale

### Prérequis
- Python 3.10 ou supérieur
- Un compte e-mail avec accès IMAP/SMTP (idéalement un mot de passe
  d'application dédié, pas le mot de passe principal du compte)

### Étapes

1. **Cloner et entrer dans le dossier**
   ```bash
   git clone <url-du-depot>
   cd ai-email-responder
   ```

2. **Créer et activer un environnement virtuel**
   ```bash
   python -m venv venv
   source venv/bin/activate      # macOS/Linux
   venv\Scripts\activate         # Windows
   ```

3. **Installer les dépendances**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configurer les variables d'environnement**
   ```bash
   cp .env.example .env
   ```
   Puis éditer `.env` avec vos vraies valeurs (serveurs IMAP/SMTP,
   identifiants, `SECRET_KEY`, `TRIGGER_TOKEN`). `python-dotenv` charge ce
   fichier automatiquement si vous ajoutez `from dotenv import load_dotenv;
   load_dotenv()` en tête de `app.py`, ou exportez les variables vous-même
   dans votre shell avant de lancer l'application.

5. **Initialiser la base de données locale**
   ```bash
   python init_db.py
   ```
   Ce script vous demande un mot de passe, le hache avec Werkzeug (PBKDF2),
   et crée `data/data.json` avec un compte `admin`, une base de réponses
   vide et un `trigger_token` par défaut.

6. **Lancer l'application**
   ```bash
   flask --app app run --debug
   ```
   Ouvrez `http://127.0.0.1:5000`. La page d'accueil est publique ; le
   tableau de bord nécessite une connexion avec le compte créé à l'étape 5.

7. **Tester le traitement du courrier**
   Depuis le tableau de bord, cliquez sur « Traiter la boîte maintenant »,
   ou appelez directement :
   ```bash
   curl "http://127.0.0.1:5000/trigger_poll?token=VOTRE_TRIGGER_TOKEN"
   ```

---

## 3. Déploiement sur GitHub puis Vercel

1. **Pousser sur GitHub**
   - Vérifiez que `.env` et `data/data.json` sont bien ignorés (voir
     `.gitignore`) avant de committer — ils contiennent des secrets.
   - `git init && git add . && git commit -m "Initial commit"`
   - Créez un dépôt sur GitHub puis `git push`.

2. **Importer le projet dans Vercel**
   - Depuis le tableau de bord Vercel : *New Project* → sélectionner le
     dépôt GitHub. Vercel détecte `vercel.json` et utilise le runtime
     `@vercel/python`.

3. **Configurer les variables d'environnement sur Vercel**
   Dans *Project Settings → Environment Variables*, ajoutez les mêmes clés
   que `.env.example` (`SECRET_KEY`, `IMAP_*`, `SMTP_*`, `TRIGGER_TOKEN`),
   plus **`DATA_JSON`** : le contenu complet de votre `data/data.json` local
   (compte admin haché + base de réponses), collé comme une seule chaîne
   JSON. `utils.load_data()`/`save_data()` lisent et écrivent cette variable
   en mémoire quand elle est présente, car le système de fichiers Vercel
   n'est pas persistant entre les invocations.

   > Important : toute modification faite depuis le tableau de bord en
   > production (ajout/suppression d'une réponse) ne sera conservée que le
   > temps de vie de l'instance serverless, tant que `DATA_JSON` n'est pas
   > mise à jour manuellement dans les paramètres Vercel. Pour un usage
   > intensif du CRUD en production, prévoyez de migrer vers une vraie base
   > de données (SQLite sur un volume externe, ou un service comme
   > Vercel Postgres/Upstash) — le JSON convient pour un usage personnel et
   > un volume de réponses réduit.

4. **Déployer**
   Vercel construit et déploie automatiquement à chaque push sur la branche
   principale. Notez l'URL de production.

5. **Planifier l'appel à `/trigger_poll`**
   Vercel ne fait pas tourner de processus en arrière-plan en continu.
   Utilisez :
   - **Vercel Cron Jobs** (fichier `vercel.json` avec une section `crons`,
     disponible sur les plans qui le supportent), ou
   - un service externe gratuit (cron-job.org, EasyCron...) qui appelle
     régulièrement :
     ```
     https://votre-site.vercel.app/trigger_poll?token=VOTRE_TRIGGER_TOKEN
     ```

---

## 4. Protection du site contre les utilisateurs non désirés

Le projet applique déjà plusieurs mesures, et cette section explique
pourquoi et propose des compléments selon votre niveau d'exposition.

### Déjà en place dans le code

- **Mot de passe haché** (PBKDF2 via Werkzeug), jamais stocké en clair.
- **Sessions signées** par `SECRET_KEY`, cookies marqués `HttpOnly`,
  `SameSite=Lax` et `Secure` en production (empêche le vol de session par
  script tiers ou par un site externe).
- **Limitation des tentatives de connexion** : après 5 échecs depuis la même
  adresse IP, la connexion est bloquée 5 minutes (voir `utils.py`). C'est une
  première barrière contre le bourrage d'identifiants (credential stuffing) ;
  elle est en mémoire, donc réinitialisée à chaque redémarrage d'instance
  serverless — voir le point suivant pour la renforcer.
- **Jeton de déclenchement (`TRIGGER_TOKEN`)** comparé en temps constant
  (`hmac.compare_digest`) pour l'endpoint public `/trigger_poll`, évitant les
  attaques par mesure de temps de réponse.
- **En-têtes de sécurité** (`X-Frame-Options`, `X-Content-Type-Options`,
  `Referrer-Policy`) sur chaque réponse.
- **Toutes les routes `/api/*` sauf `/api/login`** exigent une session active
  (`@login_required`).

### À ajouter selon votre besoin

| Mesure | Pourquoi | Où |
|---|---|---|
| **Pare-feu / rate limiting au niveau plateforme** | La protection en mémoire de `utils.py` ne résiste pas à un attaquant distribué ou à des cold starts répétés. Vercel propose un pare-feu applicatif (WAF) et du rate limiting par IP dans les paramètres du projet (plan Pro). | Vercel → Project → Firewall |
| **Authentification à deux facteurs (TOTP)** | Ajoute une seconde barrière même si le mot de passe fuite. Bibliothèque légère : `pyotp`. | `utils.py` + un champ dans `data.json` |
| **Changer `TRIGGER_TOKEN` régulièrement** | Limite la fenêtre d'exploitation si le jeton fuite (logs, historique de service cron). | Variables d'environnement Vercel |
| **Restreindre `/trigger_poll` par IP source** si votre service de cron a une IP fixe | Réduit la surface d'attaque de cet endpoint public. | Middleware Flask ou pare-feu Vercel |
| **CAPTCHA sur `/login`** (ex. hCaptcha, gratuit) si le site est exposé publiquement et attire du trafic indésirable | Bloque les robots de bourrage d'identifiants avant même d'atteindre Flask. | `templates/login.html` + vérification côté serveur |
| **Journalisation des connexions** (réussies et échouées, avec horodatage et IP) | Permet de détecter une tentative d'intrusion a posteriori. | `utils.py`, écrire dans un fichier de log ou un service externe |
| **Rotation de `SECRET_KEY`** en cas de doute sur une fuite | Invalide immédiatement toutes les sessions actives. | Variable d'environnement Vercel |

Pour un usage personnel avec peu de visiteurs, les protections déjà codées
plus un mot de passe fort et un `TRIGGER_TOKEN` long suffisent largement. Le
CAPTCHA et le WAF ne deviennent utiles que si le site reçoit du trafic
indésirable réel (bots, scans automatisés).

---

## 5. Règles de code suivies dans ce projet

- PEP8 et docstrings au format Google sur chaque fonction publique.
- Aucun secret en dur dans le code : tout passe par des variables
  d'environnement ou par `data.json` (lui-même hors du dépôt git).
- Chaque appel réseau (IMAP, SMTP, appel IA) est encadré par `try/except`
  avec un comportement de repli explicite plutôt qu'un plantage.
- Design modulaire : la sélection de modèle (`answer_matcher`), son
  adaptation (`answer_adapter`) et l'accès au courrier (`email_processor`)
  sont des modules indépendants et testables séparément.
- Frontend en JavaScript natif (pas de framework) avec `async/await`,
  cohérent avec la contrainte de légèreté du projet.
