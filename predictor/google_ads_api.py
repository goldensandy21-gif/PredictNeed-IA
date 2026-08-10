from __future__ import annotations

import json
import re
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone

from .external_connectors import lire_token_signe, signer_token


class GoogleAdsConfigurationError(Exception):
    pass


class GoogleAdsAPIError(Exception):
    pass


def _fournisseur_google_ads():
    try:
        fournisseur = settings.PREDICTNEED_EXTERNAL_CONNECTORS["google_ads"]
    except KeyError as exc:
        raise GoogleAdsConfigurationError(
            "Google Ads n'est pas configuré dans PredictNeed IA."
        ) from exc
    return fournisseur


def _configuration_google_ads():
    fournisseur = _fournisseur_google_ads()
    valeurs_requises = {
        "client_id": fournisseur.get("client_id"),
        "client_secret": fournisseur.get("client_secret"),
        "developer_token": fournisseur.get("developer_token"),
    }
    if any(not valeur for valeur in valeurs_requises.values()):
        raise GoogleAdsConfigurationError(
            "Configuration Google Ads incomplète côté serveur."
        )
    return fournisseur


def normaliser_customer_id(value):
    customer_id = re.sub(r"\D", "", str(value or ""))
    if len(customer_id) != 10:
        raise ValueError(
            "L'identifiant Google Ads doit contenir 10 chiffres."
        )
    return customer_id


def _api_version():
    fournisseur = _fournisseur_google_ads()
    version = str(fournisseur.get("api_version") or "v25").strip()
    if not re.fullmatch(r"v\d+", version):
        raise GoogleAdsConfigurationError(
            "Version Google Ads API invalide."
        )
    return version


def _decode_http_error(exc):
    try:
        request_id = exc.headers.get("request-id", "")
    except Exception:
        request_id = ""

    try:
        raw = exc.read().decode("utf-8")
        payload = json.loads(raw)
    except Exception:
        payload = None

    message = "Erreur Google Ads API."
    details_google = []

    if isinstance(payload, dict):
        error = payload.get("error") or {}

        if isinstance(error, dict):
            message = str(error.get("message") or message)

            status = str(error.get("status") or "").strip()
            if status:
                details_google.append(f"status={status}")

            for detail in error.get("details") or []:
                if not isinstance(detail, dict):
                    continue

                for google_error in detail.get("errors") or []:
                    if not isinstance(google_error, dict):
                        continue

                    error_code = google_error.get("errorCode") or {}
                    if isinstance(error_code, dict):
                        for categorie, code in error_code.items():
                            details_google.append(
                                f"{categorie}={code}"
                            )

                    detail_message = str(
                        google_error.get("message") or ""
                    ).strip()

                    if detail_message and detail_message != message:
                        details_google.append(detail_message)

    details_google = list(dict.fromkeys(details_google))

    if details_google:
        message = (
            f"{message} | Détail Google : "
            + " ; ".join(details_google)
        )

    if request_id:
        message = f"{message} Request ID : {request_id}."

    return message


def _request_json(
    url,
    *,
    method="GET",
    headers=None,
    payload=None,
    timeout=30,
):
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    request = Request(
        url,
        data=data,
        headers=headers or {},
        method=method,
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except HTTPError as exc:
        raise GoogleAdsAPIError(
            _decode_http_error(exc)
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise GoogleAdsAPIError(
            "Google Ads est temporairement inaccessible."
        ) from exc
    except json.JSONDecodeError as exc:
        raise GoogleAdsAPIError(
            "Réponse Google Ads invalide."
        ) from exc


def _headers(access_token, *, login_customer_id=""):
    fournisseur = _configuration_google_ads()

    if not access_token:
        raise GoogleAdsAPIError(
            "Jeton d'accès Google Ads manquant."
        )

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "developer-token": fournisseur["developer_token"],
    }

    if login_customer_id:
        headers["login-customer-id"] = normaliser_customer_id(
            login_customer_id
        )
    return headers


def lister_comptes_accessibles(access_token):
    url = (
        "https://googleads.googleapis.com/"
        f"{_api_version()}/customers:listAccessibleCustomers"
    )
    payload = _request_json(
        url,
        headers=_headers(access_token),
    )

    customer_ids = []
    for resource_name in payload.get("resourceNames", []):
        customer_id = str(resource_name).rsplit("/", 1)[-1]
        try:
            customer_id = normaliser_customer_id(customer_id)
        except ValueError:
            continue
        if customer_id not in customer_ids:
            customer_ids.append(customer_id)
    return customer_ids


def rechercher(
    access_token,
    customer_id,
    query,
    *,
    login_customer_id="",
):
    customer_id = normaliser_customer_id(customer_id)
    query = str(query or "").strip()
    if not query:
        raise ValueError("La requête GAQL est vide.")

    url = (
        "https://googleads.googleapis.com/"
        f"{_api_version()}/customers/{customer_id}/googleAds:search"
    )

    results = []
    page_token = ""

    while True:
        payload = {"query": query}
        if page_token:
            payload["pageToken"] = page_token

        response = _request_json(
            url,
            method="POST",
            headers=_headers(
                access_token,
                login_customer_id=login_customer_id,
            ),
            payload=payload,
        )

        results.extend(response.get("results", []))
        page_token = response.get("nextPageToken") or ""
        if not page_token:
            break

    return results


def decrire_compte(
    access_token,
    customer_id,
    *,
    login_customer_id="",
):
    query = (
        "SELECT customer.id, customer.descriptive_name, "
        "customer.currency_code, customer.time_zone, "
        "customer.manager, customer.test_account, customer.status "
        "FROM customer LIMIT 1"
    )
    rows = rechercher(
        access_token,
        customer_id,
        query,
        login_customer_id=login_customer_id,
    )
    if not rows:
        raise GoogleAdsAPIError(
            "Le compte Google Ads n'a pas pu être décrit."
        )

    customer = rows[0].get("customer") or {}
    customer_id = normaliser_customer_id(
        customer.get("id") or customer_id
    )

    return {
        "customer_id": customer_id,
        "nom": (
            customer.get("descriptiveName")
            or f"Google Ads {customer_id}"
        ),
        "devise": customer.get("currencyCode") or "",
        "fuseau_horaire": customer.get("timeZone") or "",
        "manager": bool(customer.get("manager")),
        "test_account": bool(customer.get("testAccount")),
        "statut": customer.get("status") or "",
        "login_customer_id": (
            normaliser_customer_id(login_customer_id)
            if login_customer_id
            else ""
        ),
    }


def _enfants_manager(
    access_token,
    manager_customer_id,
    *,
    login_customer_id,
):
    query = (
        "SELECT customer_client.id, "
        "customer_client.descriptive_name, "
        "customer_client.currency_code, "
        "customer_client.time_zone, "
        "customer_client.manager, "
        "customer_client.test_account, "
        "customer_client.status, "
        "customer_client.level "
        "FROM customer_client "
        "WHERE customer_client.level <= 1"
    )

    rows = rechercher(
        access_token,
        manager_customer_id,
        query,
        login_customer_id=login_customer_id,
    )

    enfants = []
    for row in rows:
        customer = row.get("customerClient") or {}
        try:
            customer_id = normaliser_customer_id(
                customer.get("id")
            )
        except ValueError:
            continue

        if int(customer.get("level") or 0) == 0:
            continue

        enfants.append({
            "customer_id": customer_id,
            "nom": (
                customer.get("descriptiveName")
                or f"Google Ads {customer_id}"
            ),
            "devise": customer.get("currencyCode") or "",
            "fuseau_horaire": customer.get("timeZone") or "",
            "manager": bool(customer.get("manager")),
            "test_account": bool(customer.get("testAccount")),
            "statut": customer.get("status") or "",
            "login_customer_id": normaliser_customer_id(
                login_customer_id
            ),
        })

    return enfants


def decouvrir_comptes_publicitaires(access_token):
    racines = lister_comptes_accessibles(access_token)
    comptes = {}

    def ajouter_compte(compte):
        if compte["manager"]:
            return

        existant = comptes.get(compte["customer_id"])
        if existant is None:
            comptes[compte["customer_id"]] = compte
            return

        if (
            existant.get("login_customer_id")
            and not compte.get("login_customer_id")
        ):
            comptes[compte["customer_id"]] = compte

    for root_id in racines:
        root = decrire_compte(
            access_token,
            root_id,
            login_customer_id=root_id,
        )

        if not root["manager"]:
            ajouter_compte(root)
            continue

        login_customer_id = root["customer_id"]
        file_managers = [root["customer_id"]]
        managers_traites = set()

        while file_managers:
            manager_id = file_managers.pop(0)
            if manager_id in managers_traites:
                continue
            managers_traites.add(manager_id)

            enfants = _enfants_manager(
                access_token,
                manager_id,
                login_customer_id=login_customer_id,
            )

            for enfant in enfants:
                if enfant["manager"]:
                    if enfant["customer_id"] not in managers_traites:
                        file_managers.append(
                            enfant["customer_id"]
                        )
                else:
                    ajouter_compte(enfant)

    return sorted(
        comptes.values(),
        key=lambda item: (
            item.get("nom") or "",
            item["customer_id"],
        ),
    )


def rafraichir_access_token(refresh_token):
    fournisseur = _configuration_google_ads()
    if not refresh_token:
        raise GoogleAdsAPIError(
            "Jeton d'actualisation Google Ads manquant."
        )

    payload = urlencode({
        "grant_type": "refresh_token",
        "client_id": fournisseur["client_id"],
        "client_secret": fournisseur["client_secret"],
        "refresh_token": refresh_token,
    }).encode("utf-8")

    request = Request(
        fournisseur.get(
            "token_url",
            "https://oauth2.googleapis.com/token",
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
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GoogleAdsAPIError(
            "Le jeton Google Ads n'a pas pu être actualisé."
        ) from exc

    access_token = data.get("access_token")
    if not access_token:
        raise GoogleAdsAPIError(
            "Google n'a pas renvoyé de nouveau jeton d'accès."
        )
    return data


def access_token_pour_compte(compte):
    if compte.plateforme != "google_ads":
        raise ValueError(
            "Ce compte n'est pas un connecteur Google Ads."
        )

    access_token = ""
    refresh_token = ""

    if compte.access_token_signe:
        access_token = lire_token_signe(compte.access_token_signe)

    expiration_proche = (
        compte.expires_at is not None
        and compte.expires_at
        <= timezone.now() + timedelta(seconds=60)
    )

    if access_token and not expiration_proche:
        return access_token

    if compte.refresh_token_signe:
        refresh_token = lire_token_signe(compte.refresh_token_signe)

    payload = rafraichir_access_token(refresh_token)
    access_token = payload["access_token"]

    compte.access_token_signe = signer_token(access_token)

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
            "expires_at",
            "date_mise_a_jour",
        ]
    )

    return access_token

def lister_performances_campagnes(
    access_token,
    customer_id,
    *,
    login_customer_id="",
    periode="LAST_30_DAYS",
):
    periodes_autorisees = {
        "TODAY",
        "YESTERDAY",
        "LAST_7_DAYS",
        "LAST_14_DAYS",
        "LAST_30_DAYS",
        "THIS_MONTH",
        "LAST_MONTH",
    }
    if periode not in periodes_autorisees:
        raise ValueError("Période Google Ads non autorisée.")

    query = (
        "SELECT "
        "segments.date, "
        "campaign.id, "
        "campaign.name, "
        "campaign.status, "
        "campaign.advertising_channel_type, "
        "metrics.impressions, "
        "metrics.clicks, "
        "metrics.conversions, "
        "metrics.cost_micros "
        "FROM campaign "
        f"WHERE segments.date DURING {periode} "
        "AND campaign.status != 'REMOVED' "
        "ORDER BY segments.date, campaign.id"
    )
    return rechercher(
        access_token,
        customer_id,
        query,
        login_customer_id=login_customer_id,
    )
