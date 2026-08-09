import json
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core import signing
from django.db.models import Count
from django.urls import reverse
from django.utils import timezone

from .models import CampagneExterne, JournalSynchronisationConnecteur, SessionVisiteur


class ConnecteurConfigurationError(Exception):
    pass


class ConnecteurOAuthError(Exception):
    pass


def fournisseurs_connecteurs():
    return settings.PREDICTNEED_EXTERNAL_CONNECTORS


def get_fournisseur(plateforme):
    try:
        fournisseur = fournisseurs_connecteurs()[plateforme]
    except KeyError as exc:
        raise ConnecteurConfigurationError("Plateforme inconnue.") from exc

    return fournisseur


def fournisseur_est_configure(plateforme):
    fournisseur = get_fournisseur(plateforme)
    return bool(
        fournisseur.get("client_id")
        and fournisseur.get("client_secret")
        and fournisseur.get("auth_url")
        and fournisseur.get("token_url")
    )


def statut_configuration_fournisseurs():
    statuts = []

    for plateforme, fournisseur in fournisseurs_connecteurs().items():
        variables_requises = fournisseur.get("variables_requises", [])
        variables_optionnelles = fournisseur.get("variables_optionnelles", [])
        statuts.append({
            "plateforme": plateforme,
            "nom": fournisseur["nom"],
            "description": fournisseur["description"],
            "configure": fournisseur_est_configure(plateforme),
            "scopes": ", ".join(fournisseur.get("scopes", [])),
            "variables_requises": variables_requises,
            "variables_optionnelles": variables_optionnelles,
        })

    return statuts


def redirect_uri_connecteur(request, plateforme):
    path = reverse("connecteur_oauth_callback", args=[plateforme])

    if settings.PREDICTNEED_SITE_URL:
        return f"{settings.PREDICTNEED_SITE_URL}{path}"

    return request.build_absolute_uri(path)


def signer_state_connecteur(request, plateforme, site_id=None):
    payload = {
        "plateforme": plateforme,
        "user_id": request.user.id,
        "client_id": request.user.client_professionnel.id,
        "site_id": site_id,
        "iat": timezone.now().isoformat(),
    }
    return signing.dumps(payload, salt="predictneed-connecteur-oauth")


def verifier_state_connecteur(state):
    return signing.loads(
        state,
        salt="predictneed-connecteur-oauth",
        max_age=15 * 60,
    )


def construire_url_autorisation(request, plateforme, site_id=None):
    fournisseur = get_fournisseur(plateforme)

    if not fournisseur_est_configure(plateforme):
        raise ConnecteurConfigurationError(
            f"{fournisseur['nom']} n'est pas encore configuré côté serveur."
        )

    params = {
        "response_type": "code",
        "client_id": fournisseur["client_id"],
        "redirect_uri": redirect_uri_connecteur(request, plateforme),
        "scope": " ".join(fournisseur.get("scopes", [])),
        "state": signer_state_connecteur(request, plateforme, site_id=site_id),
    }
    params.update(fournisseur.get("extra_auth_params", {}))

    return f"{fournisseur['auth_url']}?{urlencode(params)}"


def echanger_code_contre_token(request, plateforme, code):
    fournisseur = get_fournisseur(plateforme)

    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": fournisseur["client_id"],
        "client_secret": fournisseur["client_secret"],
        "redirect_uri": redirect_uri_connecteur(request, plateforme),
    }
    payload.update(fournisseur.get("extra_token_params", {}))

    request_token = Request(
        fournisseur["token_url"],
        data=urlencode(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with urlopen(request_token, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            details = exc.read().decode("utf-8")
        except Exception:
            details = str(exc)
        raise ConnecteurOAuthError(details) from exc
    except (URLError, TimeoutError) as exc:
        raise ConnecteurOAuthError(str(exc)) from exc


def signer_token(token):
    if not token:
        return ""
    return signing.dumps(token, salt="predictneed-connecteur-token")


def lire_token_signe(token_signe):
    if not token_signe:
        return ""
    return signing.loads(token_signe, salt="predictneed-connecteur-token")


def calculer_expiration(token_payload):
    expires_in = token_payload.get("expires_in")

    if not expires_in:
        return None

    try:
        return timezone.now() + timedelta(seconds=int(expires_in))
    except (TypeError, ValueError):
        return None


def sources_reconnues_pour_plateforme(plateforme):
    mapping = {
        "google_ads": ["google", "adwords", "googleads"],
        "meta_ads": ["facebook", "instagram", "meta"],
        "linkedin_ads": ["linkedin"],
        "tiktok_ads": ["tiktok"],
    }
    return mapping.get(plateforme, [])


def synchroniser_compte_depuis_utm(compte, sites):
    sources_reconnues = sources_reconnues_pour_plateforme(compte.plateforme)
    sessions = SessionVisiteur.objects.filter(site__in=sites).exclude(utm_campaign="")

    if sources_reconnues:
        sessions_filtrees = SessionVisiteur.objects.none()

        for source in sources_reconnues:
            sessions_filtrees = sessions_filtrees | sessions.filter(utm_source__icontains=source)

        sessions = sessions_filtrees.distinct()

    campagnes = (
        sessions
        .values("site", "utm_source", "utm_medium", "utm_campaign")
        .annotate(total=Count("id"))
        .order_by("-total")
    )

    total = 0
    maintenant = timezone.now()

    for campagne in campagnes:
        nom = campagne["utm_campaign"] or "Campagne sans nom"
        identifiant = (
            f"utm:{compte.plateforme}:"
            f"{campagne['utm_source'] or ''}:"
            f"{campagne['utm_medium'] or ''}:"
            f"{nom}:"
            f"{campagne['site'] or ''}"
        )

        CampagneExterne.objects.update_or_create(
            compte=compte,
            identifiant_externe=identifiant,
            defaults={
                "site_id": campagne["site"],
                "plateforme": compte.plateforme,
                "source_donnees": "utm_predictneed",
                "nom": nom,
                "statut": "Rapprochée via UTM",
                "utm_source": campagne["utm_source"] or "",
                "utm_medium": campagne["utm_medium"] or "",
                "utm_campaign": campagne["utm_campaign"] or "",
                "clics": campagne["total"],
                "donnees_brutes": {
                    "origine": "utm_predictneed",
                    "sessions_detectees": campagne["total"],
                },
                "derniere_synchro": maintenant,
            },
        )
        total += 1

    compte.derniere_synchro = maintenant
    compte.dernier_message = (
        f"{total} campagne(s) rapprochée(s) avec les UTM PredictNeed IA."
    )
    compte.save(update_fields=["derniere_synchro", "dernier_message", "date_mise_a_jour"])

    JournalSynchronisationConnecteur.objects.create(
        compte=compte,
        statut="succes",
        message=compte.dernier_message,
        details={"campagnes": total, "source": "utm_predictneed"},
    )

    return total
