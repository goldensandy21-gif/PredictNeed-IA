from django.shortcuts import get_object_or_404, render, redirect
from django.db.models import Count, Prefetch, Q
from .analyse import analyser_besoin, analyser_session_automatique
from .models import ClientProfessionnel, SiteClient, SessionVisiteur, EvenementUtilisateur, PredictionBesoin, LeadCapture,  OpportuniteCRM, AutomatisationEmail, EtapeAutomatisationEmail, EmailAutomatise, CompteConnecteExterne, CampagneExterne
from .automations import ensure_default_automation_steps, envoyer_confirmation_lead, get_or_create_lead_confirmation_automation
from .billing import (
    StripeAPIError,
    StripeConfigurationError,
    create_subscription_checkout_session,
    format_subscription_price,
    retrieve_checkout_session,
    stripe_is_configured,
    verify_stripe_signature,
)
from .external_connectors import (
    ConnecteurConfigurationError,
    ConnecteurOAuthError,
    calculer_expiration,
    construire_url_autorisation,
    echanger_code_contre_token,
    fournisseur_est_configure,
    get_fournisseur,
    signer_token,
    statut_configuration_fournisseurs,
    synchroniser_compte_depuis_utm,
    verifier_state_connecteur,
)
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import json
import re
from urllib.parse import urlparse
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core import signing
from decimal import Decimal, InvalidOperation
from datetime import timedelta
from django.utils import timezone
from django.utils.dateparse import parse_date


PUBLIC_MODULES = [
    {
        "slug": "prediction-avancee",
        "badge": "IA",
        "nom": "Prédiction avancée",
        "accroche": "Identifier les visiteurs les plus susceptibles de passer à l'action.",
        "resume": "Le module analyse les signaux de navigation pour classer les intentions, repérer les besoins probables et proposer l'action commerciale la plus adaptée.",
        "hero": "Transformez les pages consultées, les clics et le temps passé en recommandations concrètes pour vos équipes.",
        "benefices": [
            "Détection des intentions fortes, moyennes ou faibles.",
            "Priorisation des visiteurs et prospects à relancer.",
            "Recommandations lisibles pour proposer une offre, un rendez-vous ou un contenu utile.",
        ],
        "dashboard": [
            "Scores de prédiction",
            "Profils probables",
            "Actions recommandées",
            "Leads prioritaires",
        ],
        "scenario": "Un visiteur consulte plusieurs pages offres et tarifs : PredictNeed IA signale une intention forte et recommande une proposition claire.",
    },
    {
        "slug": "segmentation",
        "badge": "SEG",
        "nom": "Segmentation intelligente",
        "accroche": "Regrouper les visiteurs selon leurs comportements et leurs besoins.",
        "resume": "Le module transforme les sessions en segments exploitables : curieux, comparateurs, prospects chauds, visiteurs accompagnement ou audiences issues de campagnes.",
        "hero": "Comprenez les grands profils de votre audience sans lire manuellement chaque session.",
        "benefices": [
            "Segments automatiquement alimentés par les comportements.",
            "Lecture rapide des profils dominants.",
            "Messages et relances mieux adaptés à chaque groupe.",
        ],
        "dashboard": [
            "Segments actifs",
            "Volumes par profil",
            "Sources associées",
            "Pages clés par segment",
        ],
        "scenario": "Les visiteurs qui reviennent sur les pages prix sont regroupés dans un segment prioritaire pour une relance commerciale.",
    },
    {
        "slug": "ecommerce",
        "badge": "ECOM",
        "nom": "E-commerce",
        "accroche": "Repérer les signaux d'achat, d'hésitation et de comparaison.",
        "resume": "Le module e-commerce aide à détecter les visiteurs proches de l'achat, les abandons potentiels et les parcours qui méritent une offre ou une aide.",
        "hero": "Suivez les comportements qui précèdent une décision d'achat et intervenez au bon moment.",
        "benefices": [
            "Identification des visiteurs qui comparent les prix.",
            "Détection des parcours longs ou hésitants.",
            "Mise en avant des produits, offres ou catégories qui attirent l'attention.",
        ],
        "dashboard": [
            "Parcours produits",
            "Intentions d'achat",
            "Opportunités e-commerce",
            "Pages à optimiser",
        ],
        "scenario": "Un visiteur passe longtemps sur une fiche produit puis revient aux tarifs : le module recommande une offre ou un contact rassurant.",
    },
    {
        "slug": "visualisations",
        "badge": "DATA",
        "nom": "Visualisations avancées",
        "accroche": "Lire les performances du site avec des graphiques simples.",
        "resume": "Le module rassemble les sessions, leads, intentions et sources sous forme de vues synthétiques faciles à comprendre.",
        "hero": "Gardez une vision claire des tendances et des signaux commerciaux importants.",
        "benefices": [
            "Graphiques pour suivre l'évolution des sessions et des leads.",
            "Répartition des intentions et des sources de trafic.",
            "Funnel simple pour visualiser le passage visiteur, prédiction, lead, opportunité.",
        ],
        "dashboard": [
            "Tendances quotidiennes",
            "Funnel commercial",
            "Sources de trafic",
            "Top pages",
        ],
        "scenario": "Vous visualisez rapidement que les campagnes sociales génèrent beaucoup de visites mais peu de leads, puis ajustez votre message.",
    },
    {
        "slug": "historique",
        "badge": "HIST",
        "nom": "Historique des comportements",
        "accroche": "Comprendre ce qui s'est passé avant une conversion.",
        "resume": "Le module historique conserve les événements utiles d'une session pour relire le chemin qui a mené à une intention, un lead ou une opportunité.",
        "hero": "Reconstituez les parcours visiteurs pour comprendre les signaux qui comptent vraiment.",
        "benefices": [
            "Chronologie des pages vues, clics et temps passé.",
            "Lecture du contexte avant la capture d'un lead.",
            "Base d'analyse pour améliorer les pages et les offres.",
        ],
        "dashboard": [
            "Timeline des événements",
            "Sessions récentes",
            "Pages consultées",
            "Évolution des scores",
        ],
        "scenario": "Avant de rappeler un prospect, vous voyez qu'il a consulté l'offre premium et la page contact.",
    },
    {
        "slug": "multicanal",
        "badge": "CAN",
        "nom": "Multi-canal",
        "accroche": "Comparer les sources qui amènent les meilleurs visiteurs.",
        "resume": "Le module multi-canal rapproche les sources, référents et campagnes UTM des comportements observés dans le dashboard.",
        "hero": "Sachez quels canaux attirent des visiteurs curieux, hésitants ou prêts à convertir.",
        "benefices": [
            "Suivi des sources directes, sociales, email, recherche et campagnes.",
            "Lecture des intentions par canal.",
            "Aide à orienter les efforts marketing vers les canaux utiles.",
        ],
        "dashboard": [
            "Sources de trafic",
            "UTM campaigns",
            "Intentions par canal",
            "Leads par origine",
        ],
        "scenario": "Une newsletter génère moins de sessions qu'un réseau social, mais davantage d'intentions fortes.",
    },
    {
        "slug": "connecteurs",
        "badge": "API",
        "nom": "Connecteurs et installation",
        "accroche": "Installer PredictNeed IA sur un site et préparer les intégrations.",
        "resume": "Le module connecteurs centralise les scripts d'installation, clés API et états des connexions disponibles.",
        "hero": "Un script, une clé API, puis les premières données remontent dans le dashboard.",
        "benefices": [
            "Script d'installation par site connecté.",
            "Clé API unique pour associer les données au bon espace.",
            "Base prête pour de futurs connecteurs CRM, email ou paiement.",
        ],
        "dashboard": [
            "Scripts par site",
            "État des connexions",
            "Clés API",
            "Préparation CRM",
        ],
        "scenario": "Vous copiez le script dans votre site : PredictNeed IA commence ensuite à alimenter vos rapports après consentement visiteur.",
    },
    {
        "slug": "publicite",
        "badge": "ADS",
        "nom": "Publicité et campagnes",
        "accroche": "Relier les campagnes aux intentions détectées.",
        "resume": "Le module publicité aide à lire la qualité d'une campagne au-delà du simple trafic : intention, lead, opportunité et pages consultées.",
        "hero": "Mesurez si vos campagnes attirent seulement des visiteurs, ou de vrais prospects.",
        "benefices": [
            "Lecture des campagnes à partir des paramètres UTM.",
            "Priorisation des sources qui créent des intentions fortes.",
            "Aide à optimiser les messages publicitaires.",
        ],
        "dashboard": [
            "Campagnes UTM",
            "Intentions par campagne",
            "Leads générés",
            "Pages d'atterrissage",
        ],
        "scenario": "Une annonce attire beaucoup de clics mais peu d'intentions : vous ajustez l'offre ou la page d'arrivée.",
    },
    {
        "slug": "securite",
        "badge": "SEC",
        "nom": "Sécurité entreprise",
        "accroche": "Garder un espace professionnel maîtrisé et lisible.",
        "resume": "Le module sécurité donne une vision des accès, consentements, modules actifs et signaux à surveiller avant une mise en production.",
        "hero": "Gardez le contrôle sur les sites, les modules, les accès et les données sensibles.",
        "benefices": [
            "Vue synthétique des modules actifs par site.",
            "Suivi des leads avec consentement.",
            "Repères pour préparer une exploitation professionnelle plus sûre.",
        ],
        "dashboard": [
            "Modules actifs",
            "Leads avec consentement",
            "Sites connectés",
            "Points de vigilance",
        ],
        "scenario": "Avant de publier un nouveau site, vous vérifiez que seuls les modules nécessaires sont actifs et que les informations légales sont prêtes.",
    },
]


def get_public_module(slug):
    for module in PUBLIC_MODULES:
        if module["slug"] == slug:
            return module
    return None


def _seo_context(title, description, **extra):
    context = {
        "page_title": title,
        "page_description": description,
    }
    context.update(extra)
    return context


def _public_site_base_url(request):
    configured_url = settings.PREDICTNEED_SITE_URL

    if configured_url:
        return configured_url.rstrip("/")

    return request.build_absolute_uri("/").rstrip("/")


def _coerce_bool(value, default=False):
    if value in [True, "true", "True", "1", 1, "on", "yes", "oui"]:
        return True

    if value in [False, "false", "False", "0", 0, "off", "no", "non"]:
        return False

    return default


PUBLIC_VISITOR_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "hotmail.com",
    "live.com",
    "outlook.com",
    "icloud.com",
    "me.com",
    "msn.com",
    "orange.fr",
    "wanadoo.fr",
    "free.fr",
    "laposte.net",
    "yahoo.com",
    "yahoo.fr",
    "proton.me",
    "protonmail.com",
}

GENERIC_REFERRER_DOMAINS = {
    "google",
    "bing",
    "yahoo",
    "duckduckgo",
    "facebook",
    "instagram",
    "linkedin",
    "twitter",
    "x",
    "youtube",
    "tiktok",
    "predictneed",
}


def _domain_from_value(value):
    normalized_value = (value or "").strip().lower()

    if not normalized_value:
        return ""

    if "@" in normalized_value:
        normalized_value = normalized_value.rsplit("@", 1)[1]

    parsed = urlparse(normalized_value if "://" in normalized_value else f"//{normalized_value}")
    hostname = parsed.hostname or normalized_value.split("/", 1)[0]

    return hostname.removeprefix("www.").strip(".")


def _company_name_from_domain(value):
    domain = _domain_from_value(value)

    if not domain or domain in PUBLIC_VISITOR_DOMAINS:
        return ""

    parts = [part for part in domain.split(".") if part]

    if not parts:
        return ""

    base = parts[-2] if len(parts) >= 2 else parts[0]

    if base in GENERIC_REFERRER_DOMAINS:
        return ""

    words = [word for word in re.split(r"[-_]+", base) if word]

    return " ".join(word.upper() if len(word) <= 3 else word.capitalize() for word in words)


def _host_matches_domain(host, domain):
    normalized_host = _domain_from_value(host)
    normalized_domain = _domain_from_value(domain)

    if not normalized_host or not normalized_domain:
        return False

    return normalized_host == normalized_domain or normalized_host.endswith(f".{normalized_domain}")


def _detect_visitor_company(session_visiteur, leads_prefetch=None):
    for lead in leads_prefetch or []:
        entreprise = _company_name_from_domain(lead.email)

        if entreprise:
            return entreprise, "Email du visiteur"

    referer_host = _domain_from_value(session_visiteur.referer)
    site_domain = session_visiteur.site.domaine if session_visiteur.site else ""

    if referer_host and not _host_matches_domain(referer_host, site_domain):
        entreprise = _company_name_from_domain(referer_host)

        if entreprise:
            return entreprise, "Domaine référent"

    return "Non identifiée", "Signal insuffisant"


def _detect_client_device(user_agent):
    ua = (user_agent or "").lower()

    is_iphone = "iphone" in ua or "ipod" in ua
    is_ipad = "ipad" in ua or ("macintosh" in ua and "mobile" in ua and "safari" in ua)
    is_android = "android" in ua
    is_android_mobile = is_android and "mobile" in ua
    is_android_tablet = is_android and "mobile" not in ua

    appareil = "Desktop"

    if is_ipad:
        appareil = "Tablette iPad"
    elif is_iphone:
        appareil = "Mobile iPhone"
    elif is_android_tablet or "tablet" in ua:
        appareil = "Tablette Android"
    elif is_android_mobile or "mobile" in ua:
        appareil = "Mobile Android" if is_android else "Mobile"

    navigateur = "Inconnu"

    if "edgios" in ua or "edg/" in ua:
        navigateur = "Edge iOS" if is_iphone or is_ipad else "Edge"
    elif "crios" in ua:
        navigateur = "Chrome iOS"
    elif "fxios" in ua:
        navigateur = "Firefox iOS"
    elif "samsungbrowser" in ua:
        navigateur = "Samsung Internet"
    elif "opr/" in ua:
        navigateur = "Opera"
    elif "chrome" in ua or "chromium" in ua:
        navigateur = "Chrome"
    elif "safari" in ua:
        navigateur = "Safari iOS" if is_iphone or is_ipad else "Safari"
    elif "firefox" in ua:
        navigateur = "Firefox"

    systeme = "Inconnu"

    if is_ipad:
        systeme = "iPadOS"
    elif is_iphone:
        systeme = "iOS"
    elif is_android:
        systeme = "Android"
    elif "windows" in ua:
        systeme = "Windows"
    elif "mac" in ua:
        systeme = "macOS"
    elif "linux" in ua:
        systeme = "Linux"

    appareil_lower = appareil.lower()

    return {
        "appareil": appareil,
        "navigateur": navigateur,
        "systeme_exploitation": systeme,
        "est_mobile": "mobile" in appareil_lower,
        "est_tablette": "tablette" in appareil_lower,
        "est_desktop": "mobile" not in appareil_lower and "tablette" not in appareil_lower,
    }


def _update_session_client_info(session_visiteur, data):
    user_agent = data.get("user_agent") or session_visiteur.user_agent or ""
    detected = _detect_client_device(user_agent)
    incoming_appareil = data.get("appareil")
    incoming_navigateur = data.get("navigateur")
    incoming_systeme = data.get("systeme_exploitation")

    detected_is_mobile_context = detected["est_mobile"] or detected["est_tablette"]
    incoming_is_desktop = incoming_appareil == "Desktop"

    session_visiteur.user_agent = user_agent or session_visiteur.user_agent
    session_visiteur.referer = data.get("referer", session_visiteur.referer)

    if detected_is_mobile_context and (not incoming_appareil or incoming_is_desktop):
        session_visiteur.appareil = detected["appareil"]
    else:
        session_visiteur.appareil = incoming_appareil or session_visiteur.appareil or detected["appareil"]

    if detected_is_mobile_context and detected["navigateur"] != "Inconnu":
        session_visiteur.navigateur = detected["navigateur"]
    else:
        session_visiteur.navigateur = (
            incoming_navigateur
            or session_visiteur.navigateur
            or detected["navigateur"]
        )

    if detected_is_mobile_context and detected["systeme_exploitation"] != "Inconnu":
        session_visiteur.systeme_exploitation = detected["systeme_exploitation"]
    else:
        session_visiteur.systeme_exploitation = (
            incoming_systeme
            or session_visiteur.systeme_exploitation
            or detected["systeme_exploitation"]
        )

    session_visiteur.source_visite = data.get("source_visite", session_visiteur.source_visite)
    session_visiteur.utm_source = data.get("utm_source", session_visiteur.utm_source)
    session_visiteur.utm_medium = data.get("utm_medium", session_visiteur.utm_medium)
    session_visiteur.utm_campaign = data.get("utm_campaign", session_visiteur.utm_campaign)

    session_visiteur.est_mobile = _coerce_bool(
        data.get("est_mobile"),
        detected["est_mobile"] or session_visiteur.est_mobile
    )
    session_visiteur.est_tablette = _coerce_bool(
        data.get("est_tablette"),
        detected["est_tablette"] or session_visiteur.est_tablette
    )
    session_visiteur.est_desktop = _coerce_bool(
        data.get("est_desktop"),
        detected["est_desktop"] and not session_visiteur.est_mobile and not session_visiteur.est_tablette
    )

    appareil_lower = (session_visiteur.appareil or "").lower()

    if "mobile" in appareil_lower:
        session_visiteur.est_mobile = True
        session_visiteur.est_tablette = False
        session_visiteur.est_desktop = False
    elif "tablette" in appareil_lower:
        session_visiteur.est_mobile = False
        session_visiteur.est_tablette = True
        session_visiteur.est_desktop = False


def robots_txt(request):
    base_url = _public_site_base_url(request)
    content = "\n".join([
        "User-agent: *",
        "Disallow: /admin/",
        "Disallow: /dashboard/",
        "Disallow: /api/",
        "Disallow: /stripe/",
        "",
        f"Sitemap: {base_url}{reverse('sitemap_xml')}",
        "",
    ])
    return HttpResponse(content, content_type="text/plain; charset=utf-8")


def sitemap_xml(request):
    base_url = _public_site_base_url(request)
    lastmod = timezone.now().date().isoformat()

    public_pages = [
        ("accueil", None, "1.0", "weekly"),
        ("fonctionnalites", None, "0.9", "weekly"),
        ("prix", None, "0.9", "weekly"),
        ("simulateur", None, "0.8", "monthly"),
        ("mentions_legales", None, "0.4", "monthly"),
        ("politique_confidentialite", None, "0.4", "monthly"),
        ("conditions_generales_utilisation", None, "0.4", "monthly"),
        ("politique_cookies", None, "0.4", "monthly"),
    ]

    sitemap_urls = []

    for name, args, priority, changefreq in public_pages:
        sitemap_urls.append({
            "loc": f"{base_url}{reverse(name, args=args)}",
            "priority": priority,
            "changefreq": changefreq,
        })

    for module in PUBLIC_MODULES:
        sitemap_urls.append({
            "loc": f"{base_url}{reverse('fonctionnalite_detail', args=[module['slug']])}",
            "priority": "0.8",
            "changefreq": "monthly",
        })

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]

    for item in sitemap_urls:
        lines.extend([
            "  <url>",
            f"    <loc>{item['loc']}</loc>",
            f"    <lastmod>{lastmod}</lastmod>",
            f"    <changefreq>{item['changefreq']}</changefreq>",
            f"    <priority>{item['priority']}</priority>",
            "  </url>",
        ])

    lines.append("</urlset>")

    return HttpResponse("\n".join(lines), content_type="application/xml; charset=utf-8")


def accueil(request):
    resultat = None

    if request.method == "POST":
        if not request.session.session_key:
            request.session.create()

        session_visiteur, created = SessionVisiteur.objects.get_or_create(
            session_id=request.session.session_key
        )

        page_visitee = request.POST.get("page_visitee")
        temps = request.POST.get("temps")
        clics = request.POST.get("clics")

        resultat = analyser_besoin(page_visitee, temps, clics)

        EvenementUtilisateur.objects.create(
            session=session_visiteur,
            type_evenement="formulaire",
            page=page_visitee,
            valeur=f"Temps : {temps} | Clics : {clics}"
        )

        PredictionBesoin.objects.create(
            session=session_visiteur,
            profil=resultat["profil"],
            besoin_probable=resultat["prediction"],
            intention=resultat["intention"],
            score=resultat["score"],
            recommandation=resultat["recommandation"]
        )

    context = _seo_context(
        "PredictNeed IA - Prédiction des besoins visiteurs",
        "PredictNeed IA analyse les signaux visiteurs pour détecter les intentions, qualifier les prospects et aider les professionnels à convertir plus vite.",
        **(resultat or {}),
        modules_publics=PUBLIC_MODULES,
    )
    context.update(_subscription_context())
    return render(request, "predictor/accueil.html", context)


def fonctionnalites(request):
    return render(
        request,
        "predictor/fonctionnalites.html",
        _seo_context(
            "Fonctionnalités - PredictNeed IA",
            "Découvrez les modules PredictNeed IA : prédiction avancée, segmentation, e-commerce, visualisations, historique, multi-canal, connecteurs, publicité et sécurité.",
            modules_publics=PUBLIC_MODULES,
        ),
    )


def fonctionnalite_detail(request, slug):
    module = get_public_module(slug)

    if module is None:
        return redirect("fonctionnalites")

    autres_modules = [item for item in PUBLIC_MODULES if item["slug"] != slug][:4]

    return render(
        request,
        "predictor/fonctionnalite_detail.html",
        _seo_context(
            f"{module['nom']} - PredictNeed IA",
            module["resume"],
            module=module,
            autres_modules=autres_modules,
        ),
    )


def mentions_legales(request):
    return render(
        request,
        "predictor/mentions_legales.html",
        _seo_context(
            "Mentions légales - PredictNeed IA",
            "Consultez les informations légales de PredictNeed IA, service SaaS d'analyse comportementale et de prédiction des besoins visiteurs.",
        ),
    )


def politique_confidentialite(request):
    return render(
        request,
        "predictor/politique_confidentialite.html",
        _seo_context(
            "Politique de confidentialité RGPD - PredictNeed IA",
            "Politique de confidentialité de PredictNeed IA : données collectées, finalités, consentement, droits RGPD et durées de conservation.",
        ),
    )


def conditions_generales_utilisation(request):
    return render(
        request,
        "predictor/conditions_generales_utilisation.html",
        _seo_context(
            "Conditions générales d'utilisation - PredictNeed IA",
            "Conditions générales d'utilisation du service PredictNeed IA, abonnement, accès au dashboard, responsabilités et règles d'utilisation.",
            **_subscription_context(),
        ),
    )


def politique_cookies(request):
    return render(
        request,
        "predictor/politique_cookies.html",
        _seo_context(
            "Politique de cookies - PredictNeed IA",
            "Politique de cookies de PredictNeed IA : cookies nécessaires, mesure d'audience, choix de confidentialité et gestion du consentement.",
        ),
    )


def _subscription_context():
    return {
        "prix_abonnement": format_subscription_price(),
        "paiement_configure": stripe_is_configured(),
    }


def _absolute_url(request, route_name):
    path = reverse(route_name)
    if settings.PREDICTNEED_SITE_URL:
        return f"{settings.PREDICTNEED_SITE_URL}{path}"
    return request.build_absolute_uri(path)


def _find_existing_user_for_signup(User, username, email):
    user_by_username = User.objects.filter(username=username).first()
    user_by_email = User.objects.filter(email=email).first()

    if user_by_username and user_by_email and user_by_username.pk != user_by_email.pk:
        return None, "Ce nom d'utilisateur et cette adresse email sont déjà associés à deux comptes différents."

    existing_user = user_by_username or user_by_email
    if not existing_user:
        return None, None

    try:
        client = existing_user.client_professionnel
    except ClientProfessionnel.DoesNotExist:
        return None, "Ce compte existe déjà."

    if existing_user.is_active or client.statut_abonnement != "paiement_en_attente":
        if existing_user.username == username:
            return None, "Ce nom d'utilisateur existe déjà."
        return None, "Cette adresse email est déjà utilisée."

    return existing_user, None


def _prepare_pending_client(
    *,
    User,
    existing_user,
    username,
    email,
    password,
    nom_entreprise,
    secteur_activite,
    nom_site,
    domaine,
):
    if existing_user:
        user = existing_user
        user.username = username
        user.email = email
        user.is_active = False
        user.set_password(password)
        user.save(update_fields=["username", "email", "password", "is_active"])
    else:
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
        )
        user.is_active = False
        user.save(update_fields=["is_active"])

    client, created = ClientProfessionnel.objects.get_or_create(
        utilisateur=user,
        defaults={
            "nom_entreprise": nom_entreprise,
            "secteur_activite": secteur_activite,
            "statut_abonnement": "paiement_en_attente",
            "date_acceptation_cgu": timezone.now(),
        },
    )

    if not created:
        client.nom_entreprise = nom_entreprise
        client.secteur_activite = secteur_activite
        client.statut_abonnement = "paiement_en_attente"
        client.date_acceptation_cgu = timezone.now()
        client.save(
            update_fields=[
                "nom_entreprise",
                "secteur_activite",
                "statut_abonnement",
                "date_acceptation_cgu",
            ]
        )

    site = client.sites.order_by("date_creation").first()
    if site:
        site.nom_site = nom_site
        site.domaine = domaine
        site.actif = False
        site.save(update_fields=["nom_site", "domaine", "actif"])
    else:
        SiteClient.objects.create(
            client=client,
            nom_site=nom_site,
            domaine=domaine,
            actif=False,
        )

    return client


def _start_subscription_checkout(request, client):
    success_url = f"{_absolute_url(request, 'paiement_succes')}?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = _absolute_url(request, "paiement_annule")

    checkout_session = create_subscription_checkout_session(
        client=client,
        success_url=success_url,
        cancel_url=cancel_url,
    )

    client.stripe_checkout_session_id = checkout_session.get("id")
    client.statut_abonnement = "paiement_en_attente"
    client.save(update_fields=["stripe_checkout_session_id", "statut_abonnement"])

    return checkout_session


def _activate_client_from_checkout_session(checkout_session):
    metadata = checkout_session.get("metadata") or {}
    client_id = metadata.get("client_id") or checkout_session.get("client_reference_id")

    if not client_id:
        return None

    try:
        client = ClientProfessionnel.objects.select_related("utilisateur").get(pk=client_id)
    except (ClientProfessionnel.DoesNotExist, ValueError):
        return None

    if checkout_session.get("status") != "complete":
        return None

    payment_status = checkout_session.get("payment_status")
    if payment_status not in {"paid", "no_payment_required"}:
        return None

    now = timezone.now()
    client.statut_abonnement = "actif"
    client.stripe_customer_id = checkout_session.get("customer") or client.stripe_customer_id
    client.stripe_subscription_id = checkout_session.get("subscription") or client.stripe_subscription_id
    client.stripe_checkout_session_id = checkout_session.get("id") or client.stripe_checkout_session_id
    client.date_activation_abonnement = now
    if not client.date_acceptation_cgu:
        client.date_acceptation_cgu = now
    client.save(
        update_fields=[
            "statut_abonnement",
            "stripe_customer_id",
            "stripe_subscription_id",
            "stripe_checkout_session_id",
            "date_activation_abonnement",
            "date_acceptation_cgu",
        ]
    )

    user = client.utilisateur
    if not user.is_active:
        user.is_active = True
        user.save(update_fields=["is_active"])

    client.sites.update(actif=True)
    return client


def _update_subscription_from_stripe(subscription):
    customer_id = subscription.get("customer")
    subscription_id = subscription.get("id")
    metadata = subscription.get("metadata") or {}
    client_id = metadata.get("client_id")

    clients = ClientProfessionnel.objects.select_related("utilisateur")
    client = None

    if client_id:
        client = clients.filter(pk=client_id).first()

    if client is None and subscription_id:
        client = clients.filter(stripe_subscription_id=subscription_id).first()

    if client is None and customer_id:
        client = clients.filter(stripe_customer_id=customer_id).first()

    if client is None:
        return

    status = subscription.get("status")
    if status in {"active", "trialing"}:
        client.statut_abonnement = "actif" if status == "active" else "essai"
        client.utilisateur.is_active = True
        client.sites.update(actif=True)
    elif status in {"canceled", "incomplete_expired"}:
        client.statut_abonnement = "annule"
        client.utilisateur.is_active = False
        client.sites.update(actif=False)
    elif status in {"past_due", "unpaid", "incomplete"}:
        client.statut_abonnement = "impaye"
    else:
        client.statut_abonnement = "paiement_en_attente"

    client.stripe_customer_id = customer_id or client.stripe_customer_id
    client.stripe_subscription_id = subscription_id or client.stripe_subscription_id
    client.save(
        update_fields=[
            "statut_abonnement",
            "stripe_customer_id",
            "stripe_subscription_id",
        ]
    )
    client.utilisateur.save(update_fields=["is_active"])


def prix(request):
    return render(
        request,
        "predictor/prix.html",
        _seo_context(
            "Prix - PredictNeed IA",
            "Découvrez l'abonnement PredictNeed IA Pro à 99 euros par mois pour accéder au dashboard, aux modules avancés et au script d'analyse.",
            **_subscription_context(),
        ),
    )


def paiement_succes(request):
    session_id = request.GET.get("session_id")

    if not session_id:
        return render(
            request,
            "predictor/paiement_statut.html",
            {
                **_subscription_context(),
                "etat": "erreur",
                "titre": "Paiement introuvable",
                "message": "La session de paiement n'a pas pu être identifiée.",
            },
        )

    try:
        checkout_session = retrieve_checkout_session(session_id)
    except (StripeConfigurationError, StripeAPIError):
        return render(
            request,
            "predictor/paiement_statut.html",
            {
                **_subscription_context(),
                "etat": "erreur",
                "titre": "Vérification du paiement impossible",
                "message": "Le paiement a peut-être été validé, mais le service ne peut pas encore le confirmer. Réessayez dans quelques instants.",
            },
        )

    client = _activate_client_from_checkout_session(checkout_session)
    if client is None:
        return render(
            request,
            "predictor/paiement_statut.html",
            {
                **_subscription_context(),
                "etat": "attente",
                "titre": "Paiement en cours de confirmation",
                "message": "Votre abonnement n'est pas encore confirmé. Dès validation du paiement, l'accès pourra être activé.",
            },
        )

    login(request, client.utilisateur)
    messages.success(request, "Votre abonnement PredictNeed IA est actif.")
    return redirect("dashboard")


def paiement_annule(request):
    return render(
        request,
        "predictor/paiement_statut.html",
        {
            **_subscription_context(),
            "etat": "annule",
            "titre": "Paiement annulé",
            "message": "Votre compte n'a pas été activé. Vous pouvez relancer l'inscription et finaliser le paiement sécurisé.",
        },
    )


@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    signature = request.headers.get("Stripe-Signature", "")

    try:
        signature_ok = verify_stripe_signature(
            payload,
            signature,
            settings.STRIPE_WEBHOOK_SECRET,
        )
    except StripeConfigurationError:
        return HttpResponse(status=400)

    if not signature_ok:
        return HttpResponse(status=400)

    try:
        event = json.loads(payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return HttpResponse(status=400)

    event_type = event.get("type")
    event_object = (event.get("data") or {}).get("object") or {}

    if event_type == "checkout.session.completed":
        _activate_client_from_checkout_session(event_object)
    elif event_type in {"customer.subscription.updated", "customer.subscription.deleted"}:
        _update_subscription_from_stripe(event_object)

    return HttpResponse(status=200)


@login_required
def dashboard(request):
    client = getattr(request.user, "client_professionnel", None)

    if request.user.is_superuser and client is None:
        sites = SiteClient.objects.all()
        sessions = SessionVisiteur.objects.filter(site__isnull=False)
        predictions = PredictionBesoin.objects.filter(session__site__isnull=False)
        leads = LeadCapture.objects.all()
        opportunites = OpportuniteCRM.objects.all()
        automatisations_email = AutomatisationEmail.objects.all()
        emails_automatises = EmailAutomatise.objects.all()
        nom_client = "Administration globale"

    elif client is not None:
        sites = client.sites.all()
        sessions = SessionVisiteur.objects.filter(site__in=sites)
        predictions = PredictionBesoin.objects.filter(session__in=sessions)
        leads = LeadCapture.objects.filter(site__in=sites)
        opportunites = OpportuniteCRM.objects.filter(site__in=sites)
        automatisations_email = AutomatisationEmail.objects.filter(client=client)
        emails_automatises = EmailAutomatise.objects.filter(site__in=sites)
        nom_client = client.nom_entreprise

    else:
        sites = SiteClient.objects.none()
        sessions = SessionVisiteur.objects.none()
        predictions = PredictionBesoin.objects.none()
        leads = LeadCapture.objects.none()
        opportunites = OpportuniteCRM.objects.none()
        automatisations_email = AutomatisationEmail.objects.none()
        emails_automatises = EmailAutomatise.objects.none()
        nom_client = "Aucun espace professionnel associé"

    sites_ecommerce = sites.filter(module_ecommerce_actif=True)
    a_module_ecommerce = sites_ecommerce.exists()
    a_module_prediction_avancee = sites.filter(module_prediction_avancee_actif=True).exists()
    a_module_segmentation = sites.filter(module_segmentation_actif=True).exists()
    a_module_visualisations = sites.filter(module_visualisations_actif=True).exists()
    a_module_historique = sites.filter(module_historique_actif=True).exists()
    a_module_multicanal = sites.filter(module_multicanal_actif=True).exists()
    a_module_connecteurs = sites.filter(module_connecteurs_actif=True).exists()
    a_module_publicite = sites.filter(module_publicite_actif=True).exists()
    a_module_securite_entreprise = sites.filter(module_securite_entreprise_actif=True).exists()

    total_sites = sites.count()
    total_predictions = predictions.count()
    total_sessions = sessions.count()
    total_leads = leads.count()
    total_opportunites = opportunites.count()
    dernieres_opportunites = opportunites.order_by("-date_mise_a_jour")[:5]
    intentions_fortes = predictions.filter(intention="Forte").count()

    sessions_mobile = sessions.filter(est_mobile=True).count()
    sessions_tablette = sessions.filter(est_tablette=True).count()
    sessions_desktop = sessions.filter(est_desktop=True).count()

    sessions_rebond = sessions.filter(est_rebond=True).count()

    if total_sessions > 0:
        taux_rebond = round((sessions_rebond / total_sessions) * 100)
    else:
        taux_rebond = 0

    pages_vues_total = sum(session.nombre_pages_vues for session in sessions)
    clics_total = sum(session.nombre_clics for session in sessions)
    temps_total_secondes = sum(session.temps_total_secondes for session in sessions)

    if total_sessions > 0:
        temps_moyen_secondes = round(temps_total_secondes / total_sessions)
    else:
        temps_moyen_secondes = 0

    sources_visite = (
        sessions
        .values("source_visite")
        .annotate(total=Count("id"))
        .order_by("-total")[:5]
    )

    utm_sources = (
        sessions
        .values("utm_source")
        .annotate(total=Count("id"))
        .order_by("-total")[:5]
    )

    pages_populaires = (
        EvenementUtilisateur.objects
        .filter(
            session__in=sessions,
            type_evenement="page_vue"
        )
        .values("page")
        .annotate(total=Count("id"))
        .order_by("-total")[:10]
    )

    profils = (
        predictions
        .values("profil")
        .annotate(total=Count("id"))
        .order_by("-total")
    )

    dernieres_predictions = predictions.order_by("-date_creation")[:5]

    leads_chauds = leads.order_by("-score", "-date_creation")[:5]
    messages_visiteurs = (
        leads
        .exclude(Q(message__isnull=True) | Q(message=""))
        .select_related("site", "session")
        .order_by("-date_creation")[:8]
    )

    sessions_recentes = (
        sessions
        .select_related("site", "site__client")
        .prefetch_related(
            Prefetch(
                "evenements",
                queryset=EvenementUtilisateur.objects.filter(
                    type_evenement="page_vue"
                ).order_by("date_creation"),
                to_attr="pages_vues_prefetch",
            ),
            Prefetch(
                "leads",
                queryset=LeadCapture.objects.order_by("-date_creation"),
                to_attr="leads_prefetch",
            ),
        )
        .order_by("-derniere_activite")[:12]
    )
    sessions_visiteurs_detaillees = []

    for session_visiteur in sessions_recentes:
        pages_vues = [
            evenement.page
            for evenement in getattr(session_visiteur, "pages_vues_prefetch", [])
            if evenement.page
        ]
        pages_affichees = pages_vues[-8:]
        leads_session = list(getattr(session_visiteur, "leads_prefetch", []))
        dernier_lead = leads_session[0] if leads_session else None
        entreprise_detectee, entreprise_signal = _detect_visitor_company(
            session_visiteur,
            leads_session,
        )

        sessions_visiteurs_detaillees.append({
            "session": session_visiteur,
            "site": session_visiteur.site,
            "pages": pages_affichees,
            "pages_supplementaires": max(len(pages_vues) - len(pages_affichees), 0),
            "entreprise_detectee": entreprise_detectee,
            "entreprise_signal": entreprise_signal,
            "dernier_lead": dernier_lead,
            "message": dernier_lead.message if dernier_lead and dernier_lead.message else "",
        })

    base_url = request.build_absolute_uri("/").rstrip("/")

    scripts_installation = []
    sites_onboarding = []

    for site in sites:
        get_or_create_lead_confirmation_automation(site)

        nb_sessions_site = sessions.filter(site=site).count()
        nb_leads_site = leads.filter(site=site).count()

        site_est_actif = nb_sessions_site > 0

        if site_est_actif:
            statut_site = "Site actif"
        else:
            statut_site = "En attente d’installation"

        script = f'''<script
        src="{base_url}/static/predictor/tracker.js"
        data-api-key="{site.cle_api}"
        data-api-url="{base_url}/api/track/"
        data-lead-url="{base_url}/api/lead/"
        data-require-consent="true"
        data-privacy-url="{base_url}{reverse('politique_confidentialite')}"
        data-cookies-url="{base_url}{reverse('politique_cookies')}">
    </script>'''

        scripts_installation.append({
            "site": site,
            "script": script,
        })

        sites_onboarding.append({
            "site": site,
            "statut": statut_site,
            "est_actif": site_est_actif,
            "nb_sessions": nb_sessions_site,
            "nb_leads": nb_leads_site,
        })

    a_un_site = total_sites > 0
    a_installation_active = total_sessions > 0
    a_lead_capture = total_leads > 0

    automatisations_email = automatisations_email.select_related("site", "client").order_by(
        "site__nom_site",
        "nom"
    ).prefetch_related(
        Prefetch(
            "etapes",
            queryset=EtapeAutomatisationEmail.objects.order_by("ordre"),
        )
    )
    derniers_emails_automatises = emails_automatises.select_related(
        "site",
        "lead",
        "automatisation"
    ).order_by("-date_creation")[:8]
    total_emails_automatises = emails_automatises.count()
    emails_automatises_envoyes = emails_automatises.filter(statut="envoye").count()
    emails_automatises_erreurs = emails_automatises.filter(statut="erreur").count()
    relances_programmees = sum(
        automatisation.etapes.filter(actif=True).count()
        for automatisation in automatisations_email
    )


    return render(request, "predictor/dashboard.html", {
        "nom_client": nom_client,
        "total_sites": total_sites,
        "total_predictions": total_predictions,
        "total_sessions": total_sessions,
        "total_leads": total_leads,
        "a_module_ecommerce": a_module_ecommerce,
        "a_module_prediction_avancee": a_module_prediction_avancee,
        "a_module_segmentation": a_module_segmentation,
        "a_module_visualisations": a_module_visualisations,
        "a_module_historique": a_module_historique,
        "a_module_multicanal": a_module_multicanal,
        "a_module_connecteurs": a_module_connecteurs,
        "a_module_publicite": a_module_publicite,
        "a_module_securite_entreprise": a_module_securite_entreprise,
        "sites_ecommerce": sites_ecommerce,
        "intentions_fortes": intentions_fortes,
        "profils": profils,
        "dernieres_predictions": dernieres_predictions,
        "leads_chauds": leads_chauds,
        "messages_visiteurs": messages_visiteurs,
        "sessions_visiteurs_detaillees": sessions_visiteurs_detaillees,
        "scripts_installation": scripts_installation,
        "sites_onboarding": sites_onboarding,
        "a_un_site": a_un_site,
        "a_installation_active": a_installation_active,
        "a_lead_capture": a_lead_capture,
        "dernieres_opportunites": dernieres_opportunites,
        "total_opportunites": total_opportunites,
        "sessions_mobile": sessions_mobile,
        "sessions_tablette": sessions_tablette,
        "sessions_desktop": sessions_desktop,
        "taux_rebond": taux_rebond,
        "pages_vues_total": pages_vues_total,
        "clics_total": clics_total,
        "temps_moyen_secondes": temps_moyen_secondes,
        "sources_visite": sources_visite,
        "utm_sources": utm_sources,
        "pages_populaires": pages_populaires,
        "automatisations_email": automatisations_email,
        "derniers_emails_automatises": derniers_emails_automatises,
        "total_emails_automatises": total_emails_automatises,
        "emails_automatises_envoyes": emails_automatises_envoyes,
        "emails_automatises_erreurs": emails_automatises_erreurs,
        "relances_programmees": relances_programmees,
    })

@login_required
def creer_opportunite_depuis_lead(request, lead_id):
    if request.method != "POST":
        return redirect("dashboard")

    client = getattr(request.user, "client_professionnel", None)

    if request.user.is_superuser and client is None:
        lead = LeadCapture.objects.filter(id=lead_id).first()

    elif client is not None:
        sites = client.sites.all()
        lead = LeadCapture.objects.filter(id=lead_id, site__in=sites).first()

    else:
        lead = None

    if lead is None:
        return redirect("dashboard")

    opportunite_existante = OpportuniteCRM.objects.filter(lead=lead).first()

    if opportunite_existante is None:
        contact = lead.email or lead.telephone or lead.nom or "Lead sans contact"

        opportunite_existante = OpportuniteCRM.objects.create(
            site=lead.site,
            lead=lead,
            titre=f"Opportunité pour {contact}",
            montant_estime=0,
            etape="qualification",
            probabilite=20,
            notes=f"Lead détecté avec le profil : {lead.profil}. Intention : {lead.intention}. Score : {lead.score}."
        )

        lead.statut_suivi = "contacte"
        lead.save()

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            "success": True,
            "id": opportunite_existante.id,
            "titre": opportunite_existante.titre,
            "montant_estime": str(opportunite_existante.montant_estime).replace(".", ","),
            "probabilite": opportunite_existante.probabilite,
            "etape": opportunite_existante.etape,
            "etape_label": opportunite_existante.get_etape_display(),
            "lead_contact": lead.email or lead.telephone or "Lead sans contact",
            "notes": opportunite_existante.notes or "",
        })

    return redirect("/dashboard/?scroll=opportunites")

@login_required
def modifier_opportunite(request, opportunite_id):
    if request.method != "POST":
        return redirect("dashboard")

    client = getattr(request.user, "client_professionnel", None)

    if request.user.is_superuser and client is None:
        opportunite = OpportuniteCRM.objects.filter(id=opportunite_id).first()

    elif client is not None:
        sites = client.sites.all()
        opportunite = OpportuniteCRM.objects.filter(
            id=opportunite_id,
            site__in=sites
        ).first()

    else:
        opportunite = None

    if opportunite is None:
        return redirect("dashboard")

    montant = request.POST.get("montant_estime", "0").replace(",", ".")
    probabilite = request.POST.get("probabilite", "20")
    etape = request.POST.get("etape")
    notes = request.POST.get("notes", "")

    try:
        opportunite.montant_estime = Decimal(montant)
    except InvalidOperation:
        pass

    try:
        opportunite.probabilite = max(0, min(100, int(probabilite)))
    except ValueError:
        pass

    statuts_valides = dict(OpportuniteCRM.ETAPE_CHOICES)

    if etape in statuts_valides:
        opportunite.etape = etape

    opportunite.notes = notes
    opportunite.save()

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            "success": True,
            "montant_estime": str(opportunite.montant_estime).replace(".", ","),
            "probabilite": opportunite.probabilite,
            "etape": opportunite.etape,
            "etape_label": opportunite.get_etape_display(),
            "notes": opportunite.notes or "",
        })

    return redirect("/dashboard/?scroll=opportunites")


@login_required
def modifier_automatisation_email(request, automatisation_id):
    if request.method != "POST":
        return redirect("dashboard")

    client = getattr(request.user, "client_professionnel", None)

    if request.user.is_superuser and client is None:
        automatisation = AutomatisationEmail.objects.filter(id=automatisation_id).first()

    elif client is not None:
        automatisation = AutomatisationEmail.objects.filter(
            id=automatisation_id,
            client=client
        ).first()

    else:
        automatisation = None

    if automatisation is None:
        return redirect("dashboard")

    automatisation.nom = request.POST.get("nom", automatisation.nom).strip() or automatisation.nom
    automatisation.sujet = request.POST.get("sujet", automatisation.sujet).strip() or automatisation.sujet
    automatisation.contenu = request.POST.get("contenu", automatisation.contenu).strip() or automatisation.contenu
    automatisation.actif = request.POST.get("actif") == "on"
    automatisation.envoyer_copie_interne = request.POST.get("envoyer_copie_interne") == "on"
    automatisation.email_copie = (request.POST.get("email_copie") or "").strip() or None
    automatisation.save(
        update_fields=[
            "nom",
            "sujet",
            "contenu",
            "actif",
            "envoyer_copie_interne",
            "email_copie",
            "date_mise_a_jour",
        ]
    )
    ensure_default_automation_steps(automatisation)

    for etape in automatisation.etapes.all():
        prefix = f"etape_{etape.id}_"
        etape.nom = request.POST.get(prefix + "nom", etape.nom).strip() or etape.nom
        etape.sujet = request.POST.get(prefix + "sujet", etape.sujet).strip() or etape.sujet
        etape.contenu = request.POST.get(prefix + "contenu", etape.contenu).strip() or etape.contenu
        etape.actif = request.POST.get(prefix + "actif") == "on"
        etape.stopper_si_lead_traite = request.POST.get(prefix + "stopper_si_lead_traite") == "on"

        try:
            etape.delai_jours = max(0, int(request.POST.get(prefix + "delai_jours", etape.delai_jours)))
        except (TypeError, ValueError):
            pass

        etape.save(
            update_fields=[
                "nom",
                "sujet",
                "contenu",
                "actif",
                "stopper_si_lead_traite",
                "delai_jours",
                "date_mise_a_jour",
            ]
        )

    return redirect("/dashboard/?scroll=automatisations")


@login_required
def nettoyer_evenements(request):
    if request.method != "POST":
        return redirect("dashboard")

    client = getattr(request.user, "client_professionnel", None)

    if request.user.is_superuser and client is None:
        EvenementUtilisateur.objects.all().delete()

    elif client is not None:
        sites = client.sites.all()
        sessions = SessionVisiteur.objects.filter(site__in=sites)

        EvenementUtilisateur.objects.filter(session__in=sessions).delete()

    return redirect("dashboard")

@login_required
def changer_statut_lead(request, lead_id, nouveau_statut):
    if request.method != "POST":
        return JsonResponse({
            "success": False,
            "error": "Méthode non autorisée"
        }, status=405)

    statuts_valides = ["nouveau", "contacte", "converti", "perdu"]

    if nouveau_statut not in statuts_valides:
        return JsonResponse({
            "success": False,
            "error": "Statut invalide"
        }, status=400)

    client = getattr(request.user, "client_professionnel", None)

    if request.user.is_superuser and client is None:
        lead = LeadCapture.objects.filter(id=lead_id).first()

    elif client is not None:
        sites = client.sites.all()
        lead = LeadCapture.objects.filter(id=lead_id, site__in=sites).first()

    else:
        lead = None

    if lead is None:
        return JsonResponse({
            "success": False,
            "error": "Lead introuvable"
        }, status=404)

    lead.statut_suivi = nouveau_statut
    lead.save()

    return JsonResponse({
        "success": True,
        "statut": lead.statut_suivi,
        "label": lead.get_statut_suivi_display(),
    })

@login_required
def ajouter_site(request):
    client = getattr(request.user, "client_professionnel", None)

    if client is None:
        return redirect("dashboard")

    erreur = None

    if request.method == "POST":
        nom_site = request.POST.get("nom_site")
        domaine = request.POST.get("domaine")

        if not nom_site or not domaine:
            erreur = "Le nom du site et le domaine sont obligatoires."
        else:
            SiteClient.objects.create(
                client=client,
                nom_site=nom_site,
                domaine=domaine
            )

            return redirect("dashboard")

    return render(request, "predictor/ajouter_site.html", {
        "erreur": erreur,
    })

@csrf_exempt
def track_event(request):
    if request.method != "POST":
        return JsonResponse(
            {"success": False, "error": "Méthode non autorisée"},
            status=405
        )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "error": "Données JSON invalides"},
            status=400
        )

    api_key = data.get("api_key")
    session_id = data.get("session_id")
    type_evenement = data.get("type_evenement", "page_vue")
    page = data.get("page", "")
    valeur = data.get("valeur", "")
    consentement_tracking = data.get("consentement_tracking")

    if not api_key:
        return JsonResponse(
            {"success": False, "error": "Clé API manquante"},
            status=400
        )

    if not session_id:
        return JsonResponse(
            {"success": False, "error": "Session visiteur manquante"},
            status=400
        )

    if consentement_tracking not in [True, "true", "1", 1, "on"]:
        return JsonResponse(
            {"success": False, "error": "Consentement tracking obligatoire"},
            status=400
        )

    try:
        site = SiteClient.objects.get(cle_api=api_key, actif=True)
    except SiteClient.DoesNotExist:
        return JsonResponse(
            {"success": False, "error": "Clé API invalide"},
            status=403
        )

    session_visiteur, created = SessionVisiteur.objects.get_or_create(
        site=site,
        session_id=session_id
    )
    _update_session_client_info(session_visiteur, data)

    session_visiteur.save()

    EvenementUtilisateur.objects.create(
        session=session_visiteur,
        type_evenement=type_evenement,
        page=page,
        valeur=valeur
    )

    session_visiteur.nombre_pages_vues = EvenementUtilisateur.objects.filter(
    session=session_visiteur,
    type_evenement="page_vue"
    ).count()

    session_visiteur.nombre_clics = EvenementUtilisateur.objects.filter(
        session=session_visiteur,
        type_evenement="clic"
    ).count()

    evenements_temps = EvenementUtilisateur.objects.filter(
        session=session_visiteur,
        type_evenement="temps"
    )

    temps_total = 0

    for event in evenements_temps:
        if event.valeur:
            chiffres = "".join([c for c in event.valeur if c.isdigit()])
            if chiffres:
                temps_total += int(chiffres)

    session_visiteur.temps_total_secondes = temps_total

    session_visiteur.est_rebond = (
    session_visiteur.nombre_pages_vues <= 1
    and session_visiteur.nombre_clics == 0
    and session_visiteur.temps_total_secondes < 10
)

    session_visiteur.save()

    resultat_auto = analyser_session_automatique(session_visiteur)

    if resultat_auto["score"] >= 2:
        PredictionBesoin.objects.create(
            session=session_visiteur,
            profil=resultat_auto["profil"],
            besoin_probable=resultat_auto["prediction"],
            intention=resultat_auto["intention"],
            score=resultat_auto["score"],
            recommandation=resultat_auto["recommandation"]
        )

    return JsonResponse({
    "success": True,
    "message": "Événement enregistré",
    "site": site.nom_site,
    "session": session_visiteur.session_id,
    "prediction": resultat_auto["prediction"],
    "profil": resultat_auto["profil"],
    "intention": resultat_auto["intention"],
    "score": resultat_auto["score"],
})

def simulateur(request):
    resultat = None

    if request.method == "POST":
        if not request.session.session_key:
            request.session.create()

        session_visiteur, created = SessionVisiteur.objects.get_or_create(
            session_id=request.session.session_key
        )

        page_visitee = request.POST.get("page_visitee")
        temps = request.POST.get("temps")
        clics = request.POST.get("clics")

        resultat = analyser_besoin(page_visitee, temps, clics)

        EvenementUtilisateur.objects.create(
            session=session_visiteur,
            type_evenement="formulaire",
            page=page_visitee,
            valeur=f"Temps : {temps} | Clics : {clics}"
        )

        PredictionBesoin.objects.create(
            session=session_visiteur,
            profil=resultat["profil"],
            besoin_probable=resultat["prediction"],
            intention=resultat["intention"],
            score=resultat["score"],
            recommandation=resultat["recommandation"]
        )

    return render(
        request,
        "predictor/simulateur.html",
        _seo_context(
            "Simulateur - PredictNeed IA",
            "Testez le simulateur PredictNeed IA pour comprendre comment les comportements visiteurs peuvent révéler une intention ou un besoin probable.",
            **(resultat or {}),
        ),
    )

def connexion(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    erreur = None

    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = (request.POST.get("password") or "").strip()
        User = get_user_model()

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is None:
            user_by_username = User.objects.filter(username__iexact=username).first()

            if user_by_username:
                user = authenticate(
                    request,
                    username=user_by_username.username,
                    password=password
                )

        if user is None and "@" in username:
            user_by_email = User.objects.filter(email__iexact=username).first()

            if user_by_email:
                user = authenticate(
                    request,
                    username=user_by_email.username,
                    password=password
                )

        if user is not None:
            login(request, user)
            return redirect("dashboard")
        else:
            erreur = "Les identifiants saisis ne correspondent à aucun compte PredictNeed IA actif."

    return render(
        request,
        "predictor/connexion.html",
        _seo_context(
            "Connexion - PredictNeed IA",
            "Connectez-vous à votre espace PredictNeed IA pour consulter vos prédictions, leads, opportunités et modules d'analyse.",
            erreur=erreur,
        ),
    )


def deconnexion(request):
    logout(request)
    return redirect("accueil")

def inscription(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    erreur = None
    User = get_user_model()

    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        email = (request.POST.get("email") or "").strip().lower()
        password = request.POST.get("password") or ""
        nom_entreprise = (request.POST.get("nom_entreprise") or "").strip()
        secteur_activite = (request.POST.get("secteur_activite") or "").strip()
        nom_site = (request.POST.get("nom_site") or "").strip()
        domaine = (request.POST.get("domaine") or "").strip()
        conditions_acceptees = request.POST.get("accept_conditions") == "on"

        champs_requis = [
            username,
            email,
            password,
            nom_entreprise,
            secteur_activite,
            nom_site,
            domaine,
        ]

        if not all(champs_requis):
            erreur = "Merci de remplir tous les champs obligatoires."
        elif not conditions_acceptees:
            erreur = "Vous devez accepter les conditions d'utilisation pour créer un compte."
        elif not stripe_is_configured():
            erreur = "Le paiement sécurisé n'est pas encore configuré. L'inscription payante est momentanément indisponible."
        else:
            existing_user, erreur = _find_existing_user_for_signup(User, username, email)

            if erreur is None:
                client = _prepare_pending_client(
                    User=User,
                    existing_user=existing_user,
                    username=username,
                    email=email,
                    password=password,
                    nom_entreprise=nom_entreprise,
                    secteur_activite=secteur_activite,
                    nom_site=nom_site,
                    domaine=domaine,
                )

                try:
                    checkout_session = _start_subscription_checkout(request, client)
                except StripeConfigurationError:
                    erreur = "Le paiement sécurisé n'est pas encore configuré. L'inscription payante est momentanément indisponible."
                except StripeAPIError:
                    erreur = "Le paiement sécurisé est momentanément indisponible. Merci de réessayer dans quelques instants."
                else:
                    return redirect(checkout_session["url"])

    return render(
        request,
        "predictor/inscription.html",
        _seo_context(
            "Créer un compte - PredictNeed IA",
            "Créez un compte professionnel PredictNeed IA et activez l'abonnement pour suivre les intentions visiteurs et les opportunités commerciales.",
            erreur=erreur,
            **_subscription_context(),
        ),
    )

@csrf_exempt
def capture_lead(request):
    if request.method != "POST":
        return JsonResponse(
            {"success": False, "error": "Méthode non autorisée"},
            status=405
        )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "error": "Données JSON invalides"},
            status=400
        )

    api_key = data.get("api_key")
    session_id = data.get("session_id")
    nom = data.get("nom", "")
    email = data.get("email", "")
    telephone = data.get("telephone", "")
    message = data.get("message", "")
    page = data.get("page", "")

    consentement = data.get("consentement")

    if not api_key:
        return JsonResponse(
            {"success": False, "error": "Clé API manquante"},
            status=400
        )

    if not session_id:
        return JsonResponse(
            {"success": False, "error": "Session visiteur manquante"},
            status=400
        )

    if not email and not telephone:
        return JsonResponse(
            {"success": False, "error": "Email ou téléphone obligatoire"},
            status=400
        )

    if consentement not in [True, "true", "1", 1, "on"]:
        return JsonResponse(
            {"success": False, "error": "Consentement obligatoire"},
            status=400
        )

    try:
        site = SiteClient.objects.get(cle_api=api_key, actif=True)
    except SiteClient.DoesNotExist:
        return JsonResponse(
            {"success": False, "error": "Clé API invalide"},
            status=403
        )

    session_visiteur, created = SessionVisiteur.objects.get_or_create(
        site=site,
        session_id=session_id
    )
    _update_session_client_info(session_visiteur, data)
    session_visiteur.save()

    resultat_auto = analyser_session_automatique(session_visiteur)

    lead = LeadCapture.objects.create(
        site=site,
        session=session_visiteur,
        nom=nom,
        email=email,
        telephone=telephone,
        message=message,
        profil=resultat_auto["profil"],
        intention=resultat_auto["intention"],
        score=resultat_auto["score"],
        consentement=True
    )

    EvenementUtilisateur.objects.create(
        session=session_visiteur,
        type_evenement="lead",
        page=page,
        valeur=f"Contact laissé : {email or telephone}"
    )

    email_automatique = envoyer_confirmation_lead(lead)

    return JsonResponse({
        "success": True,
        "message": "Contact enregistré",
        "lead_id": lead.id,
        "profil": lead.profil,
        "intention": lead.intention,
        "score": lead.score,
        "email_automatique": email_automatique.statut if email_automatique else "ignore",
    })

def get_sites_utilisateur(request):
    if request.user.is_superuser:
        return SiteClient.objects.all()

    try:
        client = request.user.client_professionnel
        return client.sites.all()
    except ClientProfessionnel.DoesNotExist:
        return SiteClient.objects.none()


def get_module_scope(request, module_field=None, ecommerce=False):
    sites = get_sites_utilisateur(request)

    if ecommerce:
        sites_actifs = sites.filter(
            Q(module_ecommerce_actif=True) | Q(type_site="ecommerce")
        )
    elif module_field:
        sites_actifs = sites.filter(**{module_field: True})
    else:
        sites_actifs = sites

    selected_site_id = request.GET.get("site")
    selected_site = None
    site_selectionne_inactif = False

    if selected_site_id and selected_site_id != "all":
        selected_site = sites.filter(id=selected_site_id).first()

        if selected_site and sites_actifs.filter(id=selected_site.id).exists():
            sites_filtres = sites_actifs.filter(id=selected_site.id)
        elif selected_site:
            sites_filtres = SiteClient.objects.none()
            site_selectionne_inactif = True
        else:
            sites_filtres = sites_actifs
    else:
        sites_filtres = sites_actifs

    return {
        "sites": sites,
        "sites_actifs": sites_actifs,
        "sites_filtres": sites_filtres,
        "selected_site": selected_site,
        "selected_site_id": selected_site_id or "all",
        "site_selectionne_inactif": site_selectionne_inactif,
    }


def render_module_non_actif(request, nom_module):
    return render(request, "predictor/module_non_actif.html", {
        "nom_module": nom_module
    })


def appliquer_filtre_dates(queryset, champ_date, request):
    date_debut = request.GET.get("date_debut", "")
    date_fin = request.GET.get("date_fin", "")

    debut = parse_date(date_debut) if date_debut else None
    fin = parse_date(date_fin) if date_fin else None

    if debut:
        queryset = queryset.filter(**{f"{champ_date}__date__gte": debut})

    if fin:
        queryset = queryset.filter(**{f"{champ_date}__date__lte": fin})

    return queryset, date_debut, date_fin


def appliquer_filtre_niveau_predictions(queryset, niveau):
    if niveau == "faible":
        return queryset.filter(score__lt=3)

    if niveau == "moyen":
        return queryset.filter(score__gte=3, score__lt=6)

    if niveau == "fort":
        return queryset.filter(Q(score__gte=6) | Q(intention__iexact="Forte"))

    return queryset


def appliquer_filtre_niveau_leads(queryset, niveau):
    if niveau == "faible":
        return queryset.filter(score__lt=3)

    if niveau == "moyen":
        return queryset.filter(score__gte=3, score__lt=6)

    if niveau == "fort":
        return queryset.filter(Q(score__gte=6) | Q(intention__iexact="Forte"))

    return queryset


def extraire_montant(valeur):
    if not valeur:
        return Decimal("0")

    correspondances = re.findall(r"\d+(?:[,.]\d+)?", str(valeur))

    if not correspondances:
        return Decimal("0")

    try:
        return Decimal(correspondances[-1].replace(",", "."))
    except InvalidOperation:
        return Decimal("0")


def total_montants(evenements):
    total = Decimal("0")

    for evenement in evenements:
        total += extraire_montant(evenement.valeur)

    return total


def ajouter_largeurs(items, cle_total="total"):
    items = list(items)
    maximum = max([item.get(cle_total) or 0 for item in items], default=0)

    for item in items:
        if maximum > 0:
            item["largeur"] = round(((item.get(cle_total) or 0) / maximum) * 100)
        else:
            item["largeur"] = 0

    return items


def serie_journaliere(queryset, champ_date, nombre_jours=7):
    aujourd_hui = timezone.localdate()
    serie = []

    for index in range(nombre_jours - 1, -1, -1):
        jour = aujourd_hui - timedelta(days=index)
        total = queryset.filter(**{f"{champ_date}__date": jour}).count()

        serie.append({
            "label": jour.strftime("%d/%m"),
            "total": total,
        })

    return ajouter_largeurs(serie)

@login_required
def module_prediction_avancee(request):
    scope = get_module_scope(
        request,
        module_field="module_prediction_avancee_actif"
    )

    if not scope["sites_actifs"].exists() or scope["site_selectionne_inactif"]:
        return render_module_non_actif(request, "Prédiction avancée")

    sessions = SessionVisiteur.objects.filter(site__in=scope["sites_filtres"])

    toutes_predictions = PredictionBesoin.objects.filter(
        session__in=sessions
    ).select_related("session", "session__site")

    tous_leads = LeadCapture.objects.filter(
        site__in=scope["sites_filtres"]
    ).select_related("site", "session")

    toutes_predictions, date_debut, date_fin = appliquer_filtre_dates(
        toutes_predictions,
        "date_creation",
        request
    )
    tous_leads, _, _ = appliquer_filtre_dates(
        tous_leads,
        "date_creation",
        request
    )

    niveau = request.GET.get("niveau", "tous")

    predictions_filtrees = appliquer_filtre_niveau_predictions(
        toutes_predictions,
        niveau
    )
    leads_filtres = appliquer_filtre_niveau_leads(tous_leads, niveau)

    total_predictions = predictions_filtrees.count()
    total_leads = leads_filtres.count()

    intentions_fortes = predictions_filtrees.filter(
        Q(score__gte=6) | Q(intention__iexact="Forte")
    ).count()
    leads_prioritaires = leads_filtres.filter(score__gte=5).order_by(
        "-score",
        "-date_creation"
    )[:10]

    score_moyen = 0

    if total_predictions > 0:
        score_moyen = round(
            sum(prediction.score for prediction in predictions_filtrees) / total_predictions,
            1
        )

    predictions = predictions_filtrees.order_by("-date_creation")[:50]
    leads = leads_filtres.order_by("-score", "-date_creation")[:20]

    return render(request, "predictor/module_prediction_avancee.html", {
        "sites": scope["sites_actifs"],
        "selected_site_id": scope["selected_site_id"],
        "date_debut": date_debut,
        "date_fin": date_fin,
        "niveau": niveau,
        "predictions": predictions,
        "leads": leads,
        "total_predictions": total_predictions,
        "total_leads": total_leads,
        "intentions_fortes": intentions_fortes,
        "leads_prioritaires": leads_prioritaires,
        "score_moyen": score_moyen,
    })


@login_required
def module_segmentation(request):
    scope = get_module_scope(request, module_field="module_segmentation_actif")

    if not scope["sites_actifs"].exists() or scope["site_selectionne_inactif"]:
        return render_module_non_actif(request, "Segmentation avancée")

    sessions = SessionVisiteur.objects.filter(site__in=scope["sites_filtres"])
    sessions, date_debut, date_fin = appliquer_filtre_dates(
        sessions,
        "date_creation",
        request
    )

    session_ids = list(sessions.values_list("id", flat=True))
    prediction_segments = {
        "chauds": set(),
        "curieux": set(),
        "prets": set(),
        "hesitants": set(),
    }

    if session_ids:
        predictions_data = PredictionBesoin.objects.filter(
            session_id__in=session_ids
        ).values_list(
            "session_id",
            "score",
            "intention",
            "profil",
            "besoin_probable",
        )

        for session_id, score, intention, profil, besoin_probable in predictions_data:
            intention_normalisee = (intention or "").lower()
            profil_normalise = (profil or "").lower()
            besoin_normalise = (besoin_probable or "").lower()

            if score >= 6 or intention_normalisee == "forte":
                prediction_segments["chauds"].add(session_id)
                prediction_segments["prets"].add(session_id)

            if "curieux" in profil_normalise or "information" in besoin_normalise:
                prediction_segments["curieux"].add(session_id)

            if "prêt" in profil_normalise or "pret" in profil_normalise:
                prediction_segments["prets"].add(session_id)

            if "comparateur" in profil_normalise or "comparaison" in besoin_normalise:
                prediction_segments["hesitants"].add(session_id)

        leads_chauds_ids = set(
            LeadCapture.objects.filter(
                session_id__in=session_ids,
                score__gte=7
            ).values_list("session_id", flat=True)
        )

        evenements_prix_ids = set(
            EvenementUtilisateur.objects.filter(
                session_id__in=session_ids,
                page__icontains="prix"
            ).values_list("session_id", flat=True)
        )
    else:
        leads_chauds_ids = set()
        evenements_prix_ids = set()

    prediction_segments["chauds"].update(leads_chauds_ids)
    prediction_segments["hesitants"].update(evenements_prix_ids)

    sessions_google = 0
    sessions_sociales = 0
    sessions_recurrentes = 0

    for source_visite, utm_source, nombre_pages_vues in sessions.values_list(
        "source_visite",
        "utm_source",
        "nombre_pages_vues"
    ):
        source = (source_visite or "").lower()
        utm = (utm_source or "").lower()

        if "google" in source or "google" in utm:
            sessions_google += 1

        if any(canal in source or canal in utm for canal in ["facebook", "instagram", "linkedin", "tiktok"]):
            sessions_sociales += 1

        if nombre_pages_vues >= 3:
            sessions_recurrentes += 1

    segments = [
        {
            "titre": "Visiteurs très chauds",
            "total": len(prediction_segments["chauds"]),
            "description": "Sessions avec intention forte ou lead à score élevé.",
        },
        {
            "titre": "Visiteurs curieux",
            "total": len(prediction_segments["curieux"]),
            "description": "Visiteurs surtout en phase de découverte ou d'information.",
        },
        {
            "titre": "Visiteurs prêts à acheter",
            "total": len(prediction_segments["prets"]),
            "description": "Profils à prioriser pour une relance commerciale rapide.",
        },
        {
            "titre": "Visiteurs hésitants",
            "total": len(prediction_segments["hesitants"]),
            "description": "Sessions de comparaison, souvent sensibles aux prix et garanties.",
        },
        {
            "titre": "Visiteurs venus de Google",
            "total": sessions_google,
            "description": "Trafic organique ou sponsorisé associé à Google.",
        },
        {
            "titre": "Visiteurs venus des réseaux sociaux",
            "total": sessions_sociales,
            "description": "Sessions issues des principaux canaux sociaux.",
        },
        {
            "titre": "Visiteurs intéressés par les prix",
            "total": len(evenements_prix_ids),
            "description": "Visiteurs ayant consulté une page prix, offre ou tarif.",
        },
        {
            "titre": "Visiteurs qui reviennent souvent",
            "total": sessions_recurrentes,
            "description": "Sessions avec plusieurs pages vues, signe d'intérêt répété.",
        },
    ]

    segments = ajouter_largeurs(segments)

    sessions_recentes = sessions.select_related("site").order_by("-derniere_activite")[:20]

    return render(request, "predictor/module_segmentation.html", {
        "sites": scope["sites_actifs"],
        "selected_site_id": scope["selected_site_id"],
        "date_debut": date_debut,
        "date_fin": date_fin,
        "segments": segments,
        "sessions_recentes": sessions_recentes,
    })


@login_required
def module_ecommerce(request):
    scope = get_module_scope(request, ecommerce=True)

    if not scope["sites_actifs"].exists() or scope["site_selectionne_inactif"]:
        return render_module_non_actif(request, "E-commerce")

    sessions = SessionVisiteur.objects.filter(site__in=scope["sites_filtres"])
    evenements = EvenementUtilisateur.objects.filter(session__in=sessions)
    evenements, date_debut, date_fin = appliquer_filtre_dates(
        evenements,
        "date_creation",
        request
    )

    produit_q = Q(page__icontains="produit") | Q(page__icontains="product")
    panier_q = (
        Q(page__icontains="panier") |
        Q(page__icontains="cart") |
        Q(page__icontains="checkout") |
        Q(valeur__icontains="panier") |
        Q(valeur__icontains="cart")
    )
    achat_q = (
        Q(page__icontains="achat") |
        Q(page__icontains="commande") |
        Q(page__icontains="merci") |
        Q(page__icontains="success") |
        Q(valeur__icontains="achat") |
        Q(valeur__icontains="commande")
    )

    evenements_produit = evenements.filter(produit_q)
    evenements_panier = evenements.filter(panier_q)
    evenements_achat = evenements.filter(achat_q)

    sessions_panier = SessionVisiteur.objects.filter(
        evenements__in=evenements_panier
    ).distinct()
    sessions_achat = SessionVisiteur.objects.filter(
        evenements__in=evenements_achat
    ).distinct()
    paniers_abandonnes_sessions = sessions_panier.exclude(
        id__in=sessions_achat.values("id")
    )

    produits_populaires = ajouter_largeurs(
        evenements_produit
        .values("page")
        .annotate(total=Count("id"))
        .order_by("-total")[:8]
    )

    categorie_preferee = "-"

    if produits_populaires:
        categorie_preferee = produits_populaires[0]["page"]

    clients_a_relancer = LeadCapture.objects.filter(
        site__in=scope["sites_filtres"],
        score__gte=5
    ).order_by("-score", "-date_creation")[:10]

    opportunites_ecommerce = OpportuniteCRM.objects.filter(
        site__in=scope["sites_filtres"]
    ).order_by("-date_mise_a_jour")[:10]

    return render(request, "predictor/module_ecommerce.html", {
        "sites": scope["sites_actifs"],
        "selected_site_id": scope["selected_site_id"],
        "date_debut": date_debut,
        "date_fin": date_fin,
        "produits_consultes": evenements_produit.count(),
        "produits_ajoutes_panier": evenements_panier.count(),
        "paniers_abandonnes": paniers_abandonnes_sessions.count(),
        "achats_realises": evenements_achat.count(),
        "montant_total_panier": total_montants(evenements_panier),
        "montant_perdu_estime": total_montants(
            evenements_panier.filter(session__in=paniers_abandonnes_sessions)
        ),
        "categorie_preferee": categorie_preferee,
        "clients_a_relancer": clients_a_relancer,
        "opportunites_ecommerce": opportunites_ecommerce,
        "produits_populaires": produits_populaires,
    })


@login_required
def module_visualisations(request):
    scope = get_module_scope(request, module_field="module_visualisations_actif")

    if not scope["sites_actifs"].exists() or scope["site_selectionne_inactif"]:
        return render_module_non_actif(request, "Visualisations avancées")

    sessions = SessionVisiteur.objects.filter(site__in=scope["sites_filtres"])
    predictions = PredictionBesoin.objects.filter(session__in=sessions)
    leads = LeadCapture.objects.filter(site__in=scope["sites_filtres"])
    opportunites = OpportuniteCRM.objects.filter(site__in=scope["sites_filtres"])
    evenements = EvenementUtilisateur.objects.filter(session__in=sessions)

    sessions, date_debut, date_fin = appliquer_filtre_dates(
        sessions,
        "date_creation",
        request
    )
    predictions, _, _ = appliquer_filtre_dates(predictions, "date_creation", request)
    leads, _, _ = appliquer_filtre_dates(leads, "date_creation", request)
    opportunites, _, _ = appliquer_filtre_dates(opportunites, "date_creation", request)
    evenements, _, _ = appliquer_filtre_dates(evenements, "date_creation", request)

    intentions_fortes_qs = predictions.filter(
        Q(score__gte=6) | Q(intention__iexact="Forte")
    )
    clics = evenements.filter(type_evenement="clic")

    total_sessions = sessions.count()
    total_clics = clics.count()
    total_leads = leads.count()
    total_opportunites = opportunites.count()

    maximum_funnel = max(total_sessions, total_clics, total_leads, total_opportunites, 1)

    funnel = [
        {"label": "Visites", "total": total_sessions},
        {"label": "Clics", "total": total_clics},
        {"label": "Leads", "total": total_leads},
        {"label": "Opportunités", "total": total_opportunites},
    ]

    for etape in funnel:
        etape["largeur"] = round((etape["total"] / maximum_funnel) * 100)

    sources = ajouter_largeurs(
        sessions
        .values("source_visite")
        .annotate(total=Count("id"))
        .order_by("-total")[:6]
    )

    pages = ajouter_largeurs(
        evenements
        .filter(type_evenement="page_vue")
        .values("page")
        .annotate(total=Count("id"))
        .order_by("-total")[:8]
    )

    return render(request, "predictor/module_visualisations.html", {
        "sites": scope["sites_actifs"],
        "selected_site_id": scope["selected_site_id"],
        "date_debut": date_debut,
        "date_fin": date_fin,
        "total_sessions": total_sessions,
        "total_leads": total_leads,
        "intentions_fortes": intentions_fortes_qs.count(),
        "sources": sources,
        "pages": pages,
        "funnel": funnel,
        "serie_visiteurs": serie_journaliere(sessions, "date_creation", 7),
        "serie_leads": serie_journaliere(leads, "date_creation", 7),
        "serie_intentions": serie_journaliere(intentions_fortes_qs, "date_creation", 7),
    })


@login_required
def module_historique(request):
    scope = get_module_scope(request, module_field="module_historique_actif")

    if not scope["sites_actifs"].exists() or scope["site_selectionne_inactif"]:
        return render_module_non_actif(request, "Historique")

    periode = request.GET.get("periode", "7j")
    aujourd_hui = timezone.localdate()
    premier_jour_mois = aujourd_hui.replace(day=1)

    if periode == "aujourdhui":
        date_debut = aujourd_hui
        date_fin = aujourd_hui
    elif periode == "30j":
        date_debut = aujourd_hui - timedelta(days=29)
        date_fin = aujourd_hui
    elif periode == "mois":
        date_debut = premier_jour_mois
        date_fin = aujourd_hui
    else:
        date_debut = aujourd_hui - timedelta(days=6)
        date_fin = aujourd_hui
        periode = "7j"

    sessions_base = SessionVisiteur.objects.filter(site__in=scope["sites_filtres"])
    predictions_base = PredictionBesoin.objects.filter(session__in=sessions_base)
    leads_base = LeadCapture.objects.filter(site__in=scope["sites_filtres"])
    opportunites_base = OpportuniteCRM.objects.filter(site__in=scope["sites_filtres"])

    def entre_dates(queryset, champ_date, debut, fin):
        return queryset.filter(
            **{
                f"{champ_date}__date__gte": debut,
                f"{champ_date}__date__lte": fin,
            }
        )

    sessions = entre_dates(sessions_base, "date_creation", date_debut, date_fin)
    predictions = entre_dates(predictions_base, "date_creation", date_debut, date_fin)
    leads = entre_dates(leads_base, "date_creation", date_debut, date_fin)
    opportunites = entre_dates(opportunites_base, "date_creation", date_debut, date_fin)

    dernier_jour_mois_precedent = premier_jour_mois - timedelta(days=1)
    premier_jour_mois_precedent = dernier_jour_mois_precedent.replace(day=1)

    predictions_mois = entre_dates(
        predictions_base,
        "date_creation",
        premier_jour_mois,
        aujourd_hui
    )
    leads_mois = entre_dates(leads_base, "date_creation", premier_jour_mois, aujourd_hui)
    opportunites_mois = entre_dates(
        opportunites_base,
        "date_creation",
        premier_jour_mois,
        aujourd_hui
    )

    predictions_mois_precedent = entre_dates(
        predictions_base,
        "date_creation",
        premier_jour_mois_precedent,
        dernier_jour_mois_precedent
    )
    leads_mois_precedent = entre_dates(
        leads_base,
        "date_creation",
        premier_jour_mois_precedent,
        dernier_jour_mois_precedent
    )
    opportunites_mois_precedent = entre_dates(
        opportunites_base,
        "date_creation",
        premier_jour_mois_precedent,
        dernier_jour_mois_precedent
    )

    jours_serie = 30 if periode in ["30j", "mois"] else 7

    return render(request, "predictor/module_historique.html", {
        "sites": scope["sites_actifs"],
        "selected_site_id": scope["selected_site_id"],
        "periode": periode,
        "date_debut": date_debut,
        "date_fin": date_fin,
        "total_sessions": sessions.count(),
        "total_predictions": predictions.count(),
        "total_leads": leads.count(),
        "total_opportunites": opportunites.count(),
        "predictions_mois": predictions_mois.count(),
        "predictions_mois_precedent": predictions_mois_precedent.count(),
        "leads_mois": leads_mois.count(),
        "leads_mois_precedent": leads_mois_precedent.count(),
        "opportunites_mois": opportunites_mois.count(),
        "opportunites_mois_precedent": opportunites_mois_precedent.count(),
        "evolution_leads": serie_journaliere(leads_base, "date_creation", jours_serie),
        "evolution_predictions": serie_journaliere(
            predictions_base,
            "date_creation",
            jours_serie
        ),
        "evolution_opportunites": serie_journaliere(
            opportunites_base,
            "date_creation",
            jours_serie
        ),
    })


@login_required
def demarrer_oauth_connecteur(request, plateforme):
    site_id = request.GET.get("site") or None

    try:
        url_autorisation = construire_url_autorisation(
            request,
            plateforme,
            site_id=site_id,
        )
    except ConnecteurConfigurationError as exc:
        messages.error(request, str(exc))
        return redirect("module_connecteurs")

    return redirect(url_autorisation)


@login_required
def connecteur_oauth_callback(request, plateforme):
    erreur = request.GET.get("error")

    if erreur:
        messages.error(
            request,
            "La connexion au compte externe a été annulée ou refusée."
        )
        return redirect("module_connecteurs")

    code = request.GET.get("code")
    state = request.GET.get("state")

    if not code or not state:
        messages.error(request, "Réponse OAuth incomplète.")
        return redirect("module_connecteurs")

    try:
        state_payload = verifier_state_connecteur(state)
    except signing.BadSignature:
        messages.error(request, "Connexion externe refusée : vérification de sécurité invalide.")
        return redirect("module_connecteurs")

    if state_payload.get("user_id") != request.user.id:
        messages.error(request, "Connexion externe refusée : utilisateur invalide.")
        return redirect("module_connecteurs")

    if state_payload.get("plateforme") != plateforme:
        messages.error(request, "Connexion externe refusée : plateforme invalide.")
        return redirect("module_connecteurs")

    try:
        fournisseur = get_fournisseur(plateforme)
        token_payload = echanger_code_contre_token(request, plateforme, code)
    except (ConnecteurConfigurationError, ConnecteurOAuthError) as exc:
        messages.error(request, f"Connexion impossible : {exc}")
        return redirect("module_connecteurs")

    client = request.user.client_professionnel
    site = None
    site_id = state_payload.get("site_id")

    if site_id:
        site = SiteClient.objects.filter(client=client, id=site_id).first()

    nom_compte = token_payload.get("account_name") or fournisseur["nom"]
    identifiant_externe = (
        token_payload.get("account_id")
        or token_payload.get("advertiser_id")
        or token_payload.get("customer_id")
    )
    access_token = token_payload.get("access_token")
    refresh_token = token_payload.get("refresh_token")

    compte, _ = CompteConnecteExterne.objects.update_or_create(
        client=client,
        plateforme=plateforme,
        identifiant_externe=identifiant_externe,
        defaults={
            "site": site,
            "nom_compte": nom_compte,
            "statut": "connecte" if access_token else "erreur",
            "scopes": " ".join(fournisseur.get("scopes", [])),
            "access_token_signe": signer_token(access_token),
            "refresh_token_signe": signer_token(refresh_token),
            "token_type": token_payload.get("token_type", "Bearer"),
            "expires_at": calculer_expiration(token_payload),
            "configuration": {
                "payload_keys": sorted(token_payload.keys()),
                "source": "oauth",
            },
            "dernier_message": (
                "Compte connecté. Vous pouvez lancer une synchronisation."
                if access_token
                else "Aucun access_token reçu par la plateforme."
            ),
        },
    )

    messages.success(
        request,
        f"{compte.get_plateforme_display()} est connecté à PredictNeed IA."
    )
    return redirect("module_connecteurs")


@login_required
@require_POST
def synchroniser_compte_connecteur(request, compte_id):
    client = request.user.client_professionnel
    compte = get_object_or_404(
        CompteConnecteExterne,
        id=compte_id,
        client=client,
    )
    sites = SiteClient.objects.filter(client=client, actif=True)

    if compte.site:
        sites = sites.filter(id=compte.site_id)

    total = synchroniser_compte_depuis_utm(compte, sites)
    messages.success(
        request,
        f"{total} campagne(s) rapprochée(s) avec les données PredictNeed IA."
    )
    return redirect("module_connecteurs")


@login_required
@require_POST
def deconnecter_compte_connecteur(request, compte_id):
    client = request.user.client_professionnel
    compte = get_object_or_404(
        CompteConnecteExterne,
        id=compte_id,
        client=client,
    )
    compte.statut = "deconnecte"
    compte.access_token_signe = ""
    compte.refresh_token_signe = ""
    compte.dernier_message = "Compte déconnecté par l'utilisateur."
    compte.save(
        update_fields=[
            "statut",
            "access_token_signe",
            "refresh_token_signe",
            "dernier_message",
            "date_mise_a_jour",
        ]
    )
    messages.success(request, "Compte externe déconnecté.")
    return redirect("module_connecteurs")


@login_required
def module_multicanal(request):
    scope = get_module_scope(request, module_field="module_multicanal_actif")

    if not scope["sites_actifs"].exists() or scope["site_selectionne_inactif"]:
        return render_module_non_actif(request, "Multi-canal")

    sessions = SessionVisiteur.objects.filter(site__in=scope["sites_filtres"])
    sessions, date_debut, date_fin = appliquer_filtre_dates(
        sessions,
        "date_creation",
        request
    )

    google_q = Q(source_visite__icontains="google") | Q(utm_source__icontains="google")
    social_q = (
        Q(source_visite__icontains="facebook") |
        Q(source_visite__icontains="instagram") |
        Q(source_visite__icontains="linkedin") |
        Q(source_visite__icontains="tiktok") |
        Q(utm_source__icontains="facebook") |
        Q(utm_source__icontains="instagram") |
        Q(utm_source__icontains="linkedin") |
        Q(utm_source__icontains="tiktok")
    )
    email_q = (
        Q(source_visite__icontains="mail") |
        Q(utm_medium__icontains="email") |
        Q(utm_source__icontains="newsletter")
    )
    direct_q = Q(source_visite__isnull=True) | Q(source_visite="") | Q(source_visite="Accès direct")

    canaux = ajouter_largeurs([
        {
            "titre": "Google",
            "total": sessions.filter(google_q).distinct().count(),
            "description": "Recherche naturelle ou campagnes Google.",
        },
        {
            "titre": "Réseaux sociaux",
            "total": sessions.filter(social_q).distinct().count(),
            "description": "Trafic social identifié par referer ou UTM.",
        },
        {
            "titre": "Email",
            "total": sessions.filter(email_q).distinct().count(),
            "description": "Newsletters, campagnes email ou liens mail.",
        },
        {
            "titre": "Accès direct",
            "total": sessions.filter(direct_q).distinct().count(),
            "description": "Visites sans source externe détectée.",
        },
    ])

    campagnes = ajouter_largeurs(
        sessions
        .exclude(utm_campaign="")
        .values("utm_campaign")
        .annotate(total=Count("id"))
        .order_by("-total")[:8]
    )

    leads_par_source = ajouter_largeurs(
        LeadCapture.objects
        .filter(site__in=scope["sites_filtres"], session__in=sessions)
        .values("session__source_visite")
        .annotate(total=Count("id"))
        .order_by("-total")[:8]
    )
    comptes_externes = CompteConnecteExterne.objects.filter(
        client=request.user.client_professionnel,
        statut="connecte"
    )

    return render(request, "predictor/module_multicanal.html", {
        "sites": scope["sites_actifs"],
        "selected_site_id": scope["selected_site_id"],
        "date_debut": date_debut,
        "date_fin": date_fin,
        "canaux": canaux,
        "campagnes": campagnes,
        "leads_par_source": leads_par_source,
        "comptes_externes": comptes_externes,
    })


@login_required
def module_connecteurs(request):
    scope = get_module_scope(request, module_field="module_connecteurs_actif")

    if not scope["sites_actifs"].exists() or scope["site_selectionne_inactif"]:
        return render_module_non_actif(request, "Connecteurs")

    sessions = SessionVisiteur.objects.filter(site__in=scope["sites_filtres"])
    leads = LeadCapture.objects.filter(site__in=scope["sites_filtres"])
    comptes_externes = CompteConnecteExterne.objects.filter(
        client=request.user.client_professionnel
    ).select_related("site")
    base_url = request.build_absolute_uri("/").rstrip("/")

    scripts_installation = []

    for site in scope["sites_filtres"]:
        scripts_installation.append({
            "site": site,
            "script": f'''<script
        src="{base_url}/static/predictor/tracker.js"
        data-api-key="{site.cle_api}"
        data-api-url="{base_url}/api/track/"
        data-lead-url="{base_url}/api/lead/"
        data-require-consent="true"
        data-privacy-url="{base_url}{reverse('politique_confidentialite')}"
        data-cookies-url="{base_url}{reverse('politique_cookies')}">
    </script>'''
        })

    fournisseurs = statut_configuration_fournisseurs()

    for fournisseur in fournisseurs:
        fournisseur["callback_url"] = (
            f"{base_url}"
            f"{reverse('connecteur_oauth_callback', args=[fournisseur['plateforme']])}"
        )
        fournisseur["connexion_url"] = reverse(
            "demarrer_oauth_connecteur",
            args=[fournisseur["plateforme"]],
        )
        if scope["selected_site_id"] and scope["selected_site_id"] != "all":
            fournisseur["connexion_url"] = (
                f"{fournisseur['connexion_url']}?site={scope['selected_site_id']}"
            )

    configuration_paiement = {
        "configure": stripe_is_configured(),
        "variables_requises": ["STRIPE_SECRET_KEY"],
        "variables_recommandees": ["STRIPE_WEBHOOK_SECRET", "STRIPE_PRICE_ID"],
        "webhook_url": f"{base_url}{reverse('stripe_webhook')}",
    }

    connecteurs = [
        {
            "nom": "Tracker JavaScript",
            "statut": "Actif" if sessions.exists() else "À installer",
            "description": "Collecte les pages vues, clics, temps passé et sources de trafic uniquement après consentement du visiteur.",
        },
        {
            "nom": "Capture de leads",
            "statut": "Actif" if leads.exists() else "Prêt",
            "description": "Enregistre les coordonnées et le consentement des prospects.",
        },
        {
            "nom": "Django Admin",
            "statut": "Actif",
            "description": "Permet de gérer clients, sites, modules, leads et opportunités.",
        },
        {
            "nom": "Comptes publicitaires externes",
            "statut": "Actif" if comptes_externes.filter(statut="connecte").exists() else "À connecter",
            "description": "Relie Google Ads, Meta Ads, LinkedIn Ads ou TikTok Ads via OAuth pour rapprocher campagnes, sources et leads.",
        },
        {
            "nom": "Stripe / Paiement",
            "statut": "Actif" if stripe_is_configured() else "À connecter",
            "description": "Gère l'abonnement mensuel PredictNeed IA Pro et l'activation du compte après paiement.",
        },
    ]

    return render(request, "predictor/module_connecteurs.html", {
        "sites": scope["sites_actifs"],
        "selected_site_id": scope["selected_site_id"],
        "connecteurs": connecteurs,
        "fournisseurs_connecteurs": fournisseurs,
        "configuration_paiement": configuration_paiement,
        "comptes_externes": comptes_externes,
        "scripts_installation": scripts_installation,
    })


@login_required
def module_publicite(request):
    scope = get_module_scope(request, module_field="module_publicite_actif")

    if not scope["sites_actifs"].exists() or scope["site_selectionne_inactif"]:
        return render_module_non_actif(request, "Publicité")

    sessions = SessionVisiteur.objects.filter(site__in=scope["sites_filtres"])
    sessions, date_debut, date_fin = appliquer_filtre_dates(
        sessions,
        "date_creation",
        request
    )

    paid_q = (
        Q(utm_medium__icontains="cpc") |
        Q(utm_medium__icontains="paid") |
        Q(utm_medium__icontains="ads") |
        Q(utm_source__icontains="google") |
        Q(utm_source__icontains="facebook") |
        Q(utm_source__icontains="meta") |
        Q(utm_source__icontains="linkedin") |
        Q(utm_source__icontains="tiktok")
    )

    sessions_publicitaires = sessions.filter(paid_q).distinct()
    leads_publicitaires = LeadCapture.objects.filter(
        site__in=scope["sites_filtres"],
        session__in=sessions_publicitaires
    )
    predictions_publicitaires = PredictionBesoin.objects.filter(
        session__in=sessions_publicitaires
    )

    campagnes = ajouter_largeurs(
        sessions_publicitaires
        .values("utm_source", "utm_medium", "utm_campaign")
        .annotate(total=Count("id"))
        .order_by("-total")[:10]
    )
    comptes_externes = CompteConnecteExterne.objects.filter(
        client=request.user.client_professionnel
    ).select_related("site")
    campagnes_externes = CampagneExterne.objects.filter(
        compte__client=request.user.client_professionnel
    ).select_related("compte", "site")[:12]

    return render(request, "predictor/module_publicite.html", {
        "sites": scope["sites_actifs"],
        "selected_site_id": scope["selected_site_id"],
        "date_debut": date_debut,
        "date_fin": date_fin,
        "sessions_publicitaires": sessions_publicitaires.count(),
        "leads_publicitaires": leads_publicitaires.count(),
        "intentions_fortes_publicitaires": predictions_publicitaires.filter(
            Q(score__gte=6) | Q(intention__iexact="Forte")
        ).count(),
        "campagnes": campagnes,
        "comptes_externes": comptes_externes,
        "campagnes_externes": campagnes_externes,
    })

@login_required
def module_securite(request):
    scope = get_module_scope(request, module_field="module_securite_entreprise_actif")

    if not scope["sites_actifs"].exists() or scope["site_selectionne_inactif"]:
        return render_module_non_actif(request, "Sécurité entreprise")

    champs_modules = [
        "module_ecommerce_actif",
        "module_prediction_avancee_actif",
        "module_segmentation_actif",
        "module_visualisations_actif",
        "module_historique_actif",
        "module_multicanal_actif",
        "module_connecteurs_actif",
        "module_publicite_actif",
        "module_securite_entreprise_actif",
    ]

    sites_securite = []

    for site in scope["sites_filtres"]:
        cle_api = str(site.cle_api)
        modules_actifs = sum(1 for champ in champs_modules if getattr(site, champ))

        sites_securite.append({
            "site": site,
            "cle_api_courte": f"{cle_api[:8]}...{cle_api[-4:]}",
            "modules_actifs": modules_actifs,
            "sessions": site.sessions.count(),
            "leads": site.leads.count(),
        })

    leads = LeadCapture.objects.filter(site__in=scope["sites_filtres"])
    sessions = SessionVisiteur.objects.filter(site__in=scope["sites_filtres"])

    return render(request, "predictor/module_securite.html", {
        "sites": scope["sites_actifs"],
        "selected_site_id": scope["selected_site_id"],
        "sites_securite": sites_securite,
        "leads_avec_consentement": leads.filter(consentement=True).count(),
        "leads_sans_consentement": leads.filter(consentement=False).count(),
        "sessions_totales": sessions.count(),
        "utilisateur_admin": request.user.is_superuser,
    })
