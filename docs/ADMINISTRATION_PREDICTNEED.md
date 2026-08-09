# Administration technique de PredictNeed IA

État documenté : 6 août 2026, avant le déploiement final.

## Architecture
- Django ; production sur Fly.io ; messagerie/domaine OVH.
- URL publique : `https://predictneed-ia.com`.
- Données séparées par `SiteClient`.
- Session unique par `(site, session_id)`.
- Clé API distincte par site.
- Modules du dashboard évalués sur le site sélectionné.
- Connecteurs OAuth rattachés à un site précis ; synchronisation limitée à ce site.
- Attribution first-touch par session : source, UTM, identifiant de clic et page d'entrée.
- Snapshot de l'attribution sur chaque opportunité liée à un lead/session.
- Vente réelle séparée du montant estimé, avec montant, devise, date, référence et attribution.
- Création/modification d'opportunité limitée au site sélectionné.

## Migrations importantes
- `0015_essai_gratuit_sans_carte` : essai 60 jours.
- `0016_newsletter_seo_lancement` : newsletter et SEO.
- `0017_securite_comptes_multisite` : sécurité comptes et multi-site.
- `0018_machine_learning_et_maintenance` : ML et maintenance.
- `0019_connecteurs_uniques_par_site` : connecteurs séparés par site.
- `0020_attribution_campagnes` : attribution first-touch et snapshot opportunité.
- `0021_ventes_reelles` : ventes réelles et chiffre d'affaires.
- `0022_mesures_regies_journalieres` : historique journalier des métriques natives des régies.

## Sécurité
- Validation Django + confirmation du mot de passe.
- Vérification email par token signé valable 7 jours.
- Réinitialisation du mot de passe par email.
- Limitation persistante en base sur routes sensibles ; clé hachée SHA-256.
- Django Admin réservé aux superutilisateurs.

## Machine learning
Commande : `python manage.py entrainer_modeles_ml`

Valeurs par défaut : 40 sessions résolues, 10 conversions, 10 pertes, balanced accuracy minimale 0,55, rappel minimal 0,40 et spécificité minimale 0,40.

Le modèle est une régression logistique supervisée séparée par site. Le scoring à règles reste le moteur de repli. Les prédictions ML enregistrent le moteur, la probabilité et la version du modèle.

Les exemples d'entraînement utilisent uniquement des résultats commerciaux résolus : lead `converti` ou `perdu`, ou opportunité liée `gagne` ou `perdu`. Lorsqu'une opportunité liée possède un résultat final, ce résultat est prioritaire sur le statut du lead. Un lead encore `contacte` peut donc être utilisable si son opportunité est déjà gagnée ou perdue.

## Conservation
Simulation : `python manage.py purge_donnees_rgpd`

Exécution : `python manage.py purge_donnees_rgpd --execute`

Valeurs par défaut : analytics détaillées 395 jours ; leads 1 095 jours.

Maintenance : `python manage.py maintenance_quotidienne`

Cette commande gère les essais, exécute la purge et nettoie les anciennes limitations de sécurité. Chaque exécution est journalisée.

## Données publicitaires natives
Les campagnes UTM restent distinguées des campagnes alimentées par API native. Les métriques natives sont stockées par campagne et par jour afin de conserver l'historique des impressions, clics, conversions et dépenses. Les totaux de `CampagneExterne` sont recalculés à partir de ces mesures journalières.

Le client REST Google Ads est séparé du flux OAuth générique. Il sait lister les comptes accessibles, parcourir les hiérarchies de comptes administrateurs, ne proposer que les comptes publicitaires non managers, paginer les requêtes GAQL et actualiser un jeton d'accès à partir du refresh token. La version d'API par défaut est `v25` et peut être remplacée avec `GOOGLE_ADS_API_VERSION`.

Après OAuth Google Ads, PredictNeed IA ne rattache aucun compte automatiquement. Les comptes publicitaires accessibles sont conservés temporairement côté session pendant 15 minutes, sans exposer les jetons OAuth dans le navigateur. Le client choisit explicitement le `customer_id` à associer au site. Le `login_customer_id` du compte administrateur est conservé lorsqu'il est nécessaire. `GOOGLE_ADS_DEVELOPER_TOKEN` est requis pour activer le bouton Google Ads.

La synchronisation Google Ads native interroge par défaut les 30 derniers jours et stocke une mesure par campagne et par date : impressions, clics, conversions et coût. `metrics.cost_micros` est converti dans la devise du compte. Les conversions restent décimales afin de ne pas perdre les conversions fractionnaires attribuées par la régie. Les autres plateformes conservent pour le moment leur rapprochement UTM tant que leur adaptateur API natif n'est pas implémenté.

## Stripe
Le code Checkout/webhook existe. La production ne doit être considérée comme prête qu'après configuration et test de `STRIPE_SECRET_KEY`, `STRIPE_PRICE_ID` et `STRIPE_WEBHOOK_SECRET`. Ne jamais stocker les secrets dans Git.

## Avant déploiement
`python manage.py check`

`python manage.py makemigrations --check --dry-run`

`python manage.py test`

`git diff --check`

Les avertissements HSTS includeSubDomains/preload restent volontairement non activés tant que tous les sous-domaines HTTPS et la décision de preload ne sont pas validés.

## Après déploiement
Vérifier `/healthz/`, migrations, comptes existants, inscription essai, simulation RGPD, maintenance manuelle, entraînement ML manuel, puis créer/mettre à jour les tâches Fly sans doublon. Configurer ensuite Stripe et Search Console.

Cette documentation technique ne remplace pas une validation juridique professionnelle.
