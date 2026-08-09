# Administration technique de PredictNeed IA

État documenté : 9 août 2026, avant le déploiement final.

## Architecture
- Django ; production sur Fly.io ; messagerie/domaine OVH.
- URL publique : `https://predictneed-ia.com`.
- Données séparées par `SiteClient`.
- Session unique par `(site, session_id)`.
- Clé API distincte par site.
- Modules du dashboard évalués sur le site sélectionné.
- Connecteurs OAuth rattachés à un site précis ; synchronisation limitée à ce site.
- Les flux temporaires de sélection de comptes publicitaires sont centralisés : durée 15 minutes, validation utilisateur/client/site, jetons signés côté serveur et conservation rétrocompatible du refresh token existant.
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

Les adaptateurs fournisseurs conservent uniquement les particularités API. Les conversions numériques, la devise par défaut et la finalisation journalisée d'une synchronisation native sont factorisées dans un utilitaire commun, afin que chaque import marque le même `dernier_message`, la même source de journal et les mêmes compteurs de campagnes/mesures.

La synchronisation Google Ads native interroge par défaut les 30 derniers jours et stocke une mesure par campagne et par date : impressions, clics, conversions et coût. `metrics.cost_micros` est converti dans la devise du compte. Les conversions restent décimales afin de ne pas perdre les conversions fractionnaires attribuées par la régie.

Les montants commerciaux et publicitaires ne sont jamais additionnés entre devises différentes. Le dashboard regroupe le chiffre d'affaires réel et attribué par code devise. Une campagne publicitaire native ne peut contenir qu'une seule devise dans son historique journalier. Le futur calcul ROAS/ROI devra comparer uniquement des montants exprimés dans la même devise, sauf ajout ultérieur d'un mécanisme explicite de conversion de change.

Les mutations du dashboard liées aux leads, opportunités, automatisations et suppressions techniques sont limitées au site explicitement sélectionné. Posséder plusieurs sites dans un même compte n'autorise pas une action déclenchée depuis le site A à modifier une ressource du site B.

Le moteur de performance publicitaire rapproche uniquement les ventes confirmées qui disposent d'une attribution déterministe vers la campagne. Pour une campagne native, l'identifiant externe peut être rapproché via `utm_id` ou via un `utm_campaign` contenant explicitement cet identifiant. Pour une campagne UTM, la campagne, la source et le medium sont comparés lorsqu'ils sont renseignés. Le ROAS correspond au chiffre d'affaires attribué divisé par la dépense publicitaire. Le ROI publicitaire correspond à `(CA attribué - dépense publicitaire) / dépense publicitaire`. Aucun ratio n'est calculé si la dépense est absente, si l'attribution n'est pas observable ou si les devises sont incompatibles. Ce ROI publicitaire n'intègre pas les coûts produits, salaires, logistique ou autres charges.

Le module Publicité affiche désormais les résultats financiers campagne par campagne à partir du moteur de performance : dépense, conversions de la régie, ventes confirmées attribuées, chiffre d'affaires attribué, ROAS, ROI publicitaire et recommandation explicable. Les filtres de dates du module s'appliquent aussi aux mesures journalières et aux ventes utilisées dans ces calculs. Une campagne dont l'attribution n'est pas observable, dont la dépense manque ou dont les devises sont incompatibles reste visible mais sans ratio financier inventé.

### Meta Ads

L'intégration Meta Ads utilise une version d'API explicite configurable avec `META_ADS_API_VERSION`, par défaut `v25.0`. La découverte des comptes publicitaires passe par le compte utilisateur autorisé et l'edge `/me/adaccounts`. PredictNeed IA conserve l'identifiant publicitaire, le nom, la devise, le fuseau horaire et le statut du compte afin de préparer une sélection explicite du compte publicitaire avant toute synchronisation native. Aucun compte Meta ne doit être choisi automatiquement lorsqu'un utilisateur en possède plusieurs.

La connexion OAuth Meta Ads ne rattache plus automatiquement un compte publicitaire. Après la découverte des comptes accessibles, PredictNeed IA crée un flux temporaire serveur valable 15 minutes et demande au client de sélectionner explicitement le compte à rattacher au site choisi. Le flux vérifie l'utilisateur, le client et le site. Les jetons OAuth restent stockés côté serveur sous forme signée et ne sont pas transmis dans le formulaire de sélection. Lors d'une reconnexion, un jeton de renouvellement déjà enregistré est conservé si Meta n'en renvoie pas un nouveau.

La synchronisation Meta Ads native interroge l'edge `act_{account_id}/insights` au niveau campagne, avec découpage journalier sur les 30 derniers jours. Elle stocke les impressions, clics, conversions disponibles, dépenses, devise et dates dans `MesureCampagneExterne`, puis recalcule les totaux de `CampagneExterne`. Les campagnes Meta sont identifiées par `campaign_id`. La synchronisation est idempotente par campagne et par date. Si le jeton Meta signé est expiré, l'utilisateur doit relancer la connexion du compte ; aucun secret OAuth n'est exposé dans le navigateur.

### LinkedIn Ads

L'intégration LinkedIn Ads utilise les endpoints REST Marketing API avec le header `Linkedin-Version`. La version par défaut est `202606` et peut être remplacée avec `LINKEDIN_ADS_API_VERSION`. Les scopes OAuth requis sont `r_ads` et `r_ads_reporting`. LinkedIn peut exiger une validation Marketing Developer Platform pour accorder ces permissions et pour fournir des refresh tokens programmatiques ; cette validation reste une action externe côté compte LinkedIn, mais le code est prêt à exploiter le refresh token lorsqu'il est présent.

Après OAuth LinkedIn Ads, PredictNeed IA découvre les comptes publicitaires accessibles via `/rest/adAccounts`, pagine les résultats et ne rattache aucun compte automatiquement. Le flux temporaire serveur de sélection reste valable 15 minutes, vérifie l'utilisateur, le client et le site, puis stocke uniquement côté serveur les jetons signés, l'identifiant `sponsoredAccount`, l'URN, le nom, la devise, le statut, le type et les informations de service du compte choisi.

La synchronisation LinkedIn Ads native lit les campagnes du compte sélectionné puis interroge `/rest/adAnalytics` au pivot campagne, granularité journalière. Elle stocke les impressions, clics de landing page, conversions externes disponibles, coût local, devise et date dans `MesureCampagneExterne`. Les campagnes LinkedIn sont identifiées par `sponsoredCampaign`. La synchronisation est idempotente par campagne et par date. Aucun fallback UTM n'est utilisé pour un compte LinkedIn Ads connecté en natif.

### TikTok Ads

L'intégration TikTok Ads utilise l'API for Business v1.3. L'URL d'autorisation est `https://ads.tiktok.com/marketing_api/auth` et l'échange du code utilise un POST JSON vers `/open_api/v1.3/oauth2/access_token/` avec `app_id`, `secret` et `auth_code`. La version par défaut est `v1.3` et peut être remplacée avec `TIKTOK_ADS_API_VERSION`. Les permissions nécessaires côté app TikTok sont au minimum la lecture des campagnes et le reporting consolidé. TikTok peut exiger une revue de l'application et une configuration explicite de l'URL de redirection avant de délivrer un `auth_code`.

Après OAuth TikTok Ads, PredictNeed IA récupère les advertisers accessibles via `/oauth2/advertiser/get/`, ou via la liste `advertiser_ids` renvoyée par l'échange token lorsque TikTok la fournit. Aucun advertiser n'est rattaché automatiquement. Le client choisit explicitement l'advertiser à associer au site ; les jetons restent stockés côté serveur sous forme signée.

La synchronisation TikTok Ads native lit `/campaign/get/`, puis `/report/integrated/get/` en rapport `BASIC`, niveau `AUCTION_CAMPAIGN`, dimensions `campaign_id` et `stat_time_day`. Elle stocke par jour les impressions, clics, conversions disponibles sous `conversion`, dépenses `spend`, devise du compte et identifiant campagne dans `MesureCampagneExterne`. La synchronisation est idempotente par campagne et par date. Aucun fallback UTM n'est utilisé pour un compte TikTok Ads connecté en natif.





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
