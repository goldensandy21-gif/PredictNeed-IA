from __future__ import annotations

import json
import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone

from .external_connectors import lire_token_signe, signer_token


class LinkedInAdsConfigurationError(Exception):
    pass


class LinkedInAdsAPIError(Exception):
    pass


PERIODES_LINKEDIN_ADS = {
    "TODAY": 0,
    "YESTERDAY": 1,
    "LAST_7_DAYS": 6,
    "LAST_14_DAYS": 13,
    "LAST_30_DAYS": 29,
}

LINKEDIN_CAMPAIGN_STATUSES = (
    "ACTIVE",
    "PAUSED",
    "DRAFT",
    "ARCHIVED",
)


def _fournisseur_linkedin_ads():
    try:
        fournisseur = settings.PREDICTNEED_EXTERNAL_CONNECTORS[
            "linkedin_ads"
        ]
    except KeyError as exc:
        raise LinkedInAdsConfigurationError(
            "LinkedIn Ads n'est pas configuré dans PredictNeed IA."
        ) from exc

    return fournisseur


def _configuration_linkedin_ads():
    fournisseur = _fournisseur_linkedin_ads()
    api_version = str(
        fournisseur.get("api_version") or "202606"
    ).strip()

    if not re.fullmatch(r"\d{6}", api_version):
        raise LinkedInAdsConfigurationError(
            "LINKEDIN_ADS_API_VERSION doit être au format YYYYMM."
        )

    return {
        **fournisseur,
        "api_version": api_version,
        "base_url": fournisseur.get(
            "base_url",
            "https://api.linkedin.com/rest",
        ).rstrip("/"),
    }


def normaliser_sponsored_account_id(value):
    account_id = str(value or "").strip()

    if account_id.startswith("urn:li:sponsoredAccount:"):
        account_id = account_id.rsplit(":", 1)[-1]

    if not account_id or not re.fullmatch(r"\d+", account_id):
        raise ValueError(
            "L'identifiant LinkedIn Ads doit être numérique."
        )

    return account_id


def normaliser_sponsored_campaign_id(value):
    campaign_id = str(value or "").strip()

    if campaign_id.startswith("urn:li:sponsoredCampaign:"):
        campaign_id = campaign_id.rsplit(":", 1)[-1]

    if not campaign_id or not re.fullmatch(r"\d+", campaign_id):
        raise ValueError(
            "L'identifiant de campagne LinkedIn Ads doit être numérique."
        )

    return campaign_id


def compte_urn(account_id):
    return (
        "urn:li:sponsoredAccount:"
        f"{normaliser_sponsored_account_id(account_id)}"
    )


def campagne_urn(campaign_id):
    return (
        "urn:li:sponsoredCampaign:"
        f"{normaliser_sponsored_campaign_id(campaign_id)}"
    )


def _headers(access_token):
    configuration = _configuration_linkedin_ads()
    token = str(access_token or "").strip()

    if not token:
        raise LinkedInAdsAPIError(
            "Jeton d'accès LinkedIn Ads manquant."
        )

    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "Linkedin-Version": configuration["api_version"],
        "X-Restli-Protocol-Version": "2.0.0",
    }


def _urlencode_restli(params):
    cleaned = {
        key: value
        for key, value in (params or {}).items()
        if value not in (None, "")
    }
    return urlencode(cleaned, safe="(),:")


def _decode_http_error(exc):
    try:
        raw = exc.read().decode("utf-8")
        payload = json.loads(raw)
    except Exception:
        payload = None

    message = "Erreur LinkedIn Ads API."
    if isinstance(payload, dict):
        service_error = (
            payload.get("message")
            or payload.get("error_description")
            or payload.get("error")
        )
        if service_error:
            message = str(service_error)

    return message


def _request_json(
    path,
    *,
    access_token,
    params=None,
    method="GET",
    payload=None,
    timeout=30,
):
    configuration = _configuration_linkedin_ads()
    path = "/" + str(path or "").lstrip("/")
    query = _urlencode_restli(params)
    url = f"{configuration['base_url']}{path}"
    if query:
        url = f"{url}?{query}"

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    request = Request(
        url,
        data=data,
        headers=_headers(access_token),
        method=method,
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except HTTPError as exc:
        raise LinkedInAdsAPIError(
            _decode_http_error(exc)
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise LinkedInAdsAPIError(
            "LinkedIn Ads est temporairement inaccessible."
        ) from exc
    except json.JSONDecodeError as exc:
        raise LinkedInAdsAPIError(
            "Réponse LinkedIn Ads invalide."
        ) from exc


def _elements(payload, message):
    elements = payload.get("elements", [])
    if not isinstance(elements, list):
        raise LinkedInAdsAPIError(message)
    return elements


def _next_page_token(payload):
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return ""
    return str(metadata.get("nextPageToken") or "").strip()


def _normaliser_compte_linkedin(item):
    if not isinstance(item, dict):
        return None

    try:
        account_id = normaliser_sponsored_account_id(
            item.get("id") or item.get("account")
        )
    except ValueError:
        return None

    nom = str(item.get("name") or "").strip()

    return {
        "account_id": account_id,
        "urn": compte_urn(account_id),
        "nom": nom or f"LinkedIn Ads {account_id}",
        "devise": str(item.get("currency") or "").strip().upper(),
        "statut": str(item.get("status") or "").strip(),
        "type": str(item.get("type") or "").strip(),
        "test_account": bool(item.get("test")),
        "serving_statuses": item.get("servingStatuses") or [],
    }


def lister_comptes_publicitaires_linkedin(access_token):
    comptes = []
    deja_vus = set()
    page_token = ""

    while True:
        params = {
            "q": "search",
            "pageSize": 100,
        }
        if page_token:
            params["pageToken"] = page_token

        payload = _request_json(
            "/adAccounts",
            access_token=access_token,
            params=params,
        )

        for item in _elements(
            payload,
            "Liste de comptes LinkedIn Ads invalide.",
        ):
            compte = _normaliser_compte_linkedin(item)
            if compte is None:
                continue
            if compte["account_id"] in deja_vus:
                continue

            deja_vus.add(compte["account_id"])
            comptes.append(compte)

        page_token = _next_page_token(payload)
        if not page_token:
            break

    return sorted(
        comptes,
        key=lambda item: (
            item.get("nom") or "",
            item["account_id"],
        ),
    )


def _normaliser_campagne_linkedin(item):
    if not isinstance(item, dict):
        return None

    try:
        campaign_id = normaliser_sponsored_campaign_id(item.get("id"))
    except ValueError:
        return None

    return {
        "campaign_id": campaign_id,
        "urn": campagne_urn(campaign_id),
        "nom": (
            str(item.get("name") or "").strip()
            or f"Campagne LinkedIn Ads {campaign_id}"
        ),
        "statut": str(item.get("status") or "").strip(),
        "account": str(item.get("account") or "").strip(),
        "raw": item,
    }


def lister_campagnes_linkedin(access_token, account_id):
    account_id = normaliser_sponsored_account_id(account_id)
    campagnes = []
    deja_vus = set()
    page_token = ""

    while True:
        params = {
            "q": "search",
            "search": (
                "(status:(values:List("
                f"{','.join(LINKEDIN_CAMPAIGN_STATUSES)}"
                ")))"
            ),
            "pageSize": 100,
        }
        if page_token:
            params["pageToken"] = page_token

        payload = _request_json(
            f"/adAccounts/{account_id}/adCampaigns",
            access_token=access_token,
            params=params,
        )

        for item in _elements(
            payload,
            "Liste de campagnes LinkedIn Ads invalide.",
        ):
            campagne = _normaliser_campagne_linkedin(item)
            if campagne is None:
                continue
            if campagne["campaign_id"] in deja_vus:
                continue

            deja_vus.add(campagne["campaign_id"])
            campagnes.append(campagne)

        page_token = _next_page_token(payload)
        if not page_token:
            break

    return campagnes


def _date_range_param(date_debut, date_fin):
    return (
        "(start:"
        f"(year:{date_debut.year},month:{date_debut.month},day:{date_debut.day}),"
        "end:"
        f"(year:{date_fin.year},month:{date_fin.month},day:{date_fin.day})"
        ")"
    )


def plage_dates_linkedin(periode):
    if periode not in PERIODES_LINKEDIN_ADS:
        raise ValueError("Période LinkedIn Ads non autorisée.")

    aujourd_hui = timezone.localdate()
    decalage = PERIODES_LINKEDIN_ADS[periode]
    if periode == "YESTERDAY":
        return aujourd_hui - timedelta(days=1), aujourd_hui - timedelta(days=1)
    return aujourd_hui - timedelta(days=decalage), aujourd_hui


def lister_performances_campagnes_linkedin(
    access_token,
    account_id,
    *,
    date_debut=None,
    date_fin=None,
    periode="LAST_30_DAYS",
):
    account_id = normaliser_sponsored_account_id(account_id)

    if date_debut is None or date_fin is None:
        date_debut, date_fin = plage_dates_linkedin(periode)

    if not isinstance(date_debut, date) or not isinstance(date_fin, date):
        raise ValueError("La plage de dates LinkedIn Ads est invalide.")

    if date_debut > date_fin:
        raise ValueError("La date de début LinkedIn Ads dépasse la date de fin.")

    lignes = []
    page_token = ""
    start = 0
    count = 1000

    while True:
        params = {
            "q": "analytics",
            "pivot": "CAMPAIGN",
            "timeGranularity": "DAILY",
            "dateRange": _date_range_param(date_debut, date_fin),
            "accounts": f"List({compte_urn(account_id)})",
            "fields": (
                "externalWebsiteConversions,dateRange,impressions,"
                "landingPageClicks,costInLocalCurrency,pivotValues"
            ),
            "count": count,
        }

        if page_token:
            params["pageToken"] = page_token
        else:
            params["start"] = start

        payload = _request_json(
            "/adAnalytics",
            access_token=access_token,
            params=params,
        )

        elements = _elements(
            payload,
            "Liste d'analytics LinkedIn Ads invalide.",
        )
        lignes.extend(
            item
            for item in elements
            if isinstance(item, dict)
        )

        page_token = _next_page_token(payload)
        if page_token:
            continue

        if len(elements) < count:
            break

        start += len(elements)

    return lignes


def _decimal(value, default="0"):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def extraire_depense_linkedin(cost_payload):
    if isinstance(cost_payload, dict):
        value = (
            cost_payload.get("amount")
            or cost_payload.get("value")
            or cost_payload.get("cost")
            or "0"
        )
        currency = (
            cost_payload.get("currencyCode")
            or cost_payload.get("currency")
            or ""
        )
    else:
        value = cost_payload
        currency = ""

    depense = _decimal(value)
    if depense < 0:
        depense = Decimal("0")

    return depense.quantize(Decimal("0.01")), str(currency or "").upper()


def rafraichir_access_token_linkedin(refresh_token):
    configuration = _configuration_linkedin_ads()
    if not refresh_token:
        raise LinkedInAdsAPIError(
            "Jeton d'actualisation LinkedIn Ads manquant."
        )

    payload = urlencode({
        "grant_type": "refresh_token",
        "client_id": configuration.get("client_id") or "",
        "client_secret": configuration.get("client_secret") or "",
        "refresh_token": refresh_token,
    }).encode("utf-8")

    request = Request(
        configuration.get(
            "token_url",
            "https://www.linkedin.com/oauth/v2/accessToken",
        ),
        data=payload,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=20) as response:
            data = json.loads(
                response.read().decode("utf-8")
            )
    except HTTPError as exc:
        raise LinkedInAdsAPIError(
            _decode_http_error(exc)
        ) from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise LinkedInAdsAPIError(
            "Le jeton LinkedIn Ads n'a pas pu être actualisé."
        ) from exc

    if not data.get("access_token"):
        raise LinkedInAdsAPIError(
            "LinkedIn n'a pas renvoyé de nouveau jeton d'accès."
        )

    return data


def access_token_pour_compte_linkedin(compte):
    if compte.plateforme != "linkedin_ads":
        raise ValueError(
            "Ce compte n'est pas un connecteur LinkedIn Ads."
        )

    access_token = lire_token_signe(compte.access_token_signe)
    expiration_proche = (
        compte.expires_at is not None
        and compte.expires_at
        <= timezone.now() + timedelta(seconds=300)
    )

    if access_token and not expiration_proche:
        return access_token

    refresh_token = lire_token_signe(compte.refresh_token_signe)
    if not refresh_token:
        raise ValueError(
            "Le jeton LinkedIn Ads est expiré. Relancez la connexion du compte ; "
            "les refresh tokens LinkedIn nécessitent l'accès Marketing Developer Platform."
        )

    payload = rafraichir_access_token_linkedin(refresh_token)
    compte.access_token_signe = signer_token(payload["access_token"])

    nouveau_refresh = payload.get("refresh_token")
    if nouveau_refresh:
        compte.refresh_token_signe = signer_token(nouveau_refresh)

    expires_in = payload.get("expires_in")
    try:
        compte.expires_at = (
            timezone.now()
            + timedelta(seconds=int(expires_in))
            if expires_in
            else None
        )
    except (TypeError, ValueError):
        compte.expires_at = None

    compte.save(
        update_fields=[
            "access_token_signe",
            "refresh_token_signe",
            "expires_at",
            "date_mise_a_jour",
        ]
    )

    return payload["access_token"]
