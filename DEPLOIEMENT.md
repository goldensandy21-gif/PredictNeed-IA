# Déploiement PredictNeed IA

Ce projet est prêt côté code pour recevoir une configuration de production, mais les secrets réels doivent être créés sur les services choisis : hébergeur, domaine, Stripe, email SMTP et connecteurs externes.

## Commandes de déploiement

Build :

```bash
pip install -r requirements.txt
python3 -B manage.py collectstatic --noinput
python3 -B manage.py migrate
```

Start :

```bash
gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
```

## Hébergement conseillé

Recommandation pour ce projet : commencer avec Render ou Scalingo.

- Render : choix simple pour un premier lancement Django avec PostgreSQL, variables d'environnement, build script, HTTPS et logs.
- Scalingo : bon choix si la priorité est un hébergement européen/français et une approche proche de Heroku avec `Procfile`.
- Railway : pratique pour tester vite et déployer rapidement un MVP, avec PostgreSQL et variables d'environnement.
- Fly.io : puissant pour une application plus technique, surtout si la localisation des régions et la performance deviennent importantes.

Éviter Vercel ou Netlify seuls pour ce projet : ils sont très bons pour des frontends statiques, mais PredictNeed IA a besoin d'un vrai serveur Django, d'une base PostgreSQL, de paiements, d'emails et de tâches automatiques.

## Variables obligatoires avant mise en ligne

Utiliser `.env.production.example` comme modèle.

- `DJANGO_DEBUG=False`
- `DJANGO_SECRET_KEY` avec une vraie clé longue et aléatoire
- `DJANGO_ALLOWED_HOSTS` avec le domaine final
- `DJANGO_CSRF_TRUSTED_ORIGINS` avec les URLs HTTPS du domaine
- `PREDICTNEED_SITE_URL` avec l’URL publique
- Variables PostgreSQL `POSTGRES_*`
- Variables Stripe `STRIPE_*`
- Variables SMTP email

## Tâches récurrentes

Programmer les relances email, par exemple toutes les heures :

```bash
python3 -B manage.py envoyer_relances_automatiques
```

## Stripe

Créer un produit/price Stripe à 99 euros par mois, puis remplir :

- `STRIPE_SECRET_KEY`
- `STRIPE_PRICE_ID`
- `STRIPE_WEBHOOK_SECRET`

Webhook Stripe à déclarer :

```text
https://ton-domaine.fr/stripe/webhook/
```

Événements Stripe utiles :

- `checkout.session.completed`
- `customer.subscription.updated`
- `customer.subscription.deleted`

## Emails

Configurer un vrai SMTP. Tant que `DJANGO_EMAIL_BACKEND` reste sur console, les emails automatiques ne partent pas réellement.

## Connecteurs externes

Les connecteurs OAuth sont prêts côté application, mais chaque plateforme demande ses propres clés développeur.

Les pixels de retargeting sont configurables par site depuis le module Connecteurs :
Meta Pixel ID, Google Ads ID, label de conversion Google, TikTok Pixel ID,
LinkedIn Partner ID, LinkedIn Conversion ID et Pinterest Tag ID. Ces valeurs ne
sont pas des secrets Fly : chaque client les renseigne dans son dashboard, puis
recopie le script PredictNeed IA mis à jour sur son site. Les pixels ne sont
chargés qu'après consentement marketing du visiteur.

URLs callback à déclarer selon le domaine :

```text
https://ton-domaine.fr/connecteurs/google_ads/callback/
https://ton-domaine.fr/connecteurs/meta_ads/callback/
https://ton-domaine.fr/connecteurs/linkedin_ads/callback/
https://ton-domaine.fr/connecteurs/tiktok_ads/callback/
```

## Vérifications avant publication

```bash
python3 -B manage.py check
DJANGO_DEBUG=False DJANGO_SECRET_KEY="une-cle-longue-et-secrete-change-moi" DJANGO_ALLOWED_HOSTS="ton-domaine.fr" DJANGO_CSRF_TRUSTED_ORIGINS="https://ton-domaine.fr" python3 -B manage.py check --deploy
```

Après choix du domaine définitif, activer aussi `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=True` et `DJANGO_SECURE_HSTS_PRELOAD=True` uniquement si tous les sous-domaines doivent rester en HTTPS.

Le site ne doit être publié que lorsque `check --deploy` ne retourne plus d’avertissement critique non compris.
