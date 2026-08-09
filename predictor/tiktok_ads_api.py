from __future__ import annotations

import json
import re
from datetime import date, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone

from .external_connectors import lire_token_signe, signer_token


class TikTokAdsConfigurationError(Exception):
    pass


class TikTokAdsAPIError(Exception):
    pass


PERIODES_TIKTOK_ADS = {
    "TODAY": 0,
    "YESTERDAY": 1,
    "LAST_7_DAYS": 6,
    "LAST_14_DAYS": 13,
    "LAST_30_DAYS": 29,
}

CAMPAIGN_FIELDS = [
    "campaign_id",
    "campaign_name",
    "operation_status",
    "secondary_status",
    "objective_type",
    "budget",
    "budget_mode",
]

REPORT_DIMENSIONS = [
    "campaign_id",
    "stat_time_day",
]

REPORT_METRICS = [
    "spend",
    "impressions",
    "clicks",
    "conversion",
]


def _fournisseur_tiktok_ads():
    try:
        fournisseur = settings.PREDICTNEED_EXTERNAL_CONNECTORS[
            "tiktok_ads"
        ]
    except KeyError as exc:
        raise TikTokAdsConfigurationError(
            "TikTok Ads n'est pas configuré dans PredictNeed IA."
        ) from exc

    return fournisseur


def _configuration_tiktok_ads():
    fournisseur = _fournisseur_tiktok_ads()
    api_version = str(fournisseur.get("api_version") or "v1.3").strip()
    if not re.fullmatch(r"v\d+\.\d+", api_version):
        raise TikTokAdsConfigurationError(
            "TIKTOK_ADS_API_VERSION doit être au format v1.3."
        )

    valeurs_requises = {
        "client_id": fournisseur.get("client_id"),
        "client_secret": fournisseur.get("client_secret"),
    }
    if any(not value for value in valeurs_requises.values()):
        raise TikTokAdsConfigurationError(
            "Configuration TikTok Ads incomplète côté serveur."
        )

    base_url = fournisseur.get(
        "base_url",
        "https://business-api.tiktok.com/open_api",
    ).rstrip("/")

    return {
        **fournisseur,
        "api_version": api_version,
        "base_url": base_url,
        "token_url": fournisseur.get("token_url")
        or f"{base_url}/{api_version}/oauth2/access_token/",
    }


def normaliser_advertiser_id(value):
    advertiser_id = str(value or "").strip()
    if not advertiser_id or not re.fullmatch(r"\d+", advertiser_id):
        raise ValueError(
            "L'identifiant advertiser TikTok Ads doit être numérique."
        )
    return advertiser_id


def normaliser_campaign_id_tiktok(value):
    campaign_id = str(value or "").strip()
    if not campaign_id or not re.fullmatch(r"\d+", campaign_id):
        raise ValueError(
            "L'identifiant de campagne TikTok Ads doit être numérique."
        )
    return campaign_id


def _param_value(value):
    if isinstance(value, (list, dict)):
        return json.dumps(value, separators=(",", ":"))
    if isinstance(value, bool):
        return str(value).lower()
    return value


def _query(params):
    cleaned = {
        key: _param_value(value)
        for key, value in (params or {}).items()
        if value not in (None, "")
    }
    return urlencode(cleaned)


def _decode_http_error(exc):
    try:
        raw = exc.read().decode("utf-8")
        payload = json.loads(raw)
    except Exception:
        payload = None

    if isinstance(payload, dict):
        return str(
            payload.get("message")
            or payload.get("error_description")
            or payload.get("error")
            or "Erreur TikTok Ads API."
        )

    return "Erreur TikTok Ads API."


def _valider_reponse_tiktok(payload):
    if not isinstance(payload, dict):
        raise TikTokAdsAPIError("Réponse TikTok Ads inattendue.")

    code = payload.get("code")
    if code not in (None, 0, "0"):
        message = payload.get("message") or "Erreur TikTok Ads API."
        request_id = payload.get("request_id") or ""
        if request_id:
            message = f"{message} Request ID : {request_id}."
        raise TikTokAdsAPIError(str(message))

    data = payload.get("data", {})
    return data if isinstance(data, (dict, list)) else {}


def _request_json_tiktok(
    path,
    *,
    access_token="",
    params=None,
    method="GET",
    payload=None,
    token_url=False,
    timeout=30,
):
    configuration = _configuration_tiktok_ads()
    if token_url:
        url = configuration["token_url"]
    else:
        path = "/" + str(path or "").lstrip("/")
        url = (
            f"{configuration['base_url']}/"
            f"{configuration['api_version']}{path}"
        )

    query = _query(params)
    if query:
        url = f"{url}?{query}"

    data = None
    headers = {
        "Accept": "application/json",
    }

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    if access_token:
        headers["Access-Token"] = access_token

    request = Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            payload_response = json.loads(body) if body else {}
    except HTTPError as exc:
        raise TikTokAdsAPIError(
            _decode_http_error(exc)
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise TikTokAdsAPIError(
            "TikTok Ads est temporairement inaccessible."
        ) from exc
    except json.JSONDecodeError as exc:
        raise TikTokAdsAPIError(
            "Réponse TikTok Ads invalide."
        ) from exc

    return _valider_reponse_tiktok(payload_response)


def echanger_code_contre_token_tiktok(code):
    configuration = _configuration_tiktok_ads()
    auth_code = str(code or "").strip()
    if not auth_code:
        raise TikTokAdsAPIError(
            "Code d'autorisation TikTok Ads manquant."
        )

    data = _request_json_tiktok(
        "/oauth2/access_token/",
        method="POST",
        token_url=True,
        payload={
            "app_id": configuration["client_id"],
            "secret": configuration["client_secret"],
            "auth_code": auth_code,
        },
    )

    access_token = data.get("access_token") if isinstance(data, dict) else ""
    if not access_token:
        raise TikTokAdsAPIError(
            "TikTok n'a pas renvoyé de jeton d'accès."
        )

    advertiser_ids = data.get("advertiser_ids") or []
    if not isinstance(advertiser_ids, list):
        advertiser_ids = []

    return {
        "access_token": access_token,
        "refresh_token": data.get("refresh_token") or "",
        "token_type": data.get("token_type") or "Bearer",
        "expires_in": data.get("expires_in"),
        "refresh_token_expires_in": data.get(
            "refresh_token_expires_in"
        ),
        "scope": data.get("scope") or [],
        "advertiser_ids": [
            str(advertiser_id)
            for advertiser_id in advertiser_ids
            if str(advertiser_id or "").strip()
        ],
        "payload_keys": sorted(data.keys()),
    }


def _normaliser_advertiser_tiktok(item):
    if isinstance(item, (str, int)):
        try:
            advertiser_id = normaliser_advertiser_id(item)
        except ValueError:
            return None
        return {
            "advertiser_id": advertiser_id,
            "nom": f"TikTok Ads {advertiser_id}",
            "devise": "",
            "fuseau_horaire": "",
            "statut": "",
            "role": "",
        }

    if not isinstance(item, dict):
        return None

    try:
        advertiser_id = normaliser_advertiser_id(
            item.get("advertiser_id")
            or item.get("id")
        )
    except ValueError:
        return None

    return {
        "advertiser_id": advertiser_id,
        "nom": (
            str(
                item.get("advertiser_name")
                or item.get("name")
                or ""
            ).strip()
            or f"TikTok Ads {advertiser_id}"
        ),
        "devise": str(
            item.get("currency")
            or item.get("currency_code")
            or ""
        ).strip().upper(),
        "fuseau_horaire": str(
            item.get("timezone")
            or item.get("time_zone")
            or ""
        ).strip(),
        "statut": str(
            item.get("status")
            or item.get("advertiser_status")
            or ""
        ).strip(),
        "role": str(
            item.get("role")
            or item.get("advertiser_role")
            or ""
        ).strip(),
    }


def _liste_depuis_data(data):
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ("list", "advertiser_ids", "campaigns"):
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []


def lister_comptes_publicitaires_tiktok(
    access_token,
    *,
    advertiser_ids=None,
):
    configuration = _configuration_tiktok_ads()
    data = _request_json_tiktok(
        "/oauth2/advertiser/get/",
        access_token=access_token,
        params={
            "app_id": configuration["client_id"],
            "secret": configuration["client_secret"],
        },
    )

    items = _liste_depuis_data(data)
    if not items and advertiser_ids:
        items = list(advertiser_ids)

    comptes = []
    deja_vus = set()
    for item in items:
        compte = _normaliser_advertiser_tiktok(item)
        if compte is None:
            continue
        if compte["advertiser_id"] in deja_vus:
            continue
        deja_vus.add(compte["advertiser_id"])
        comptes.append(compte)

    return sorted(
        comptes,
        key=lambda item: (
            item.get("nom") or "",
            item["advertiser_id"],
        ),
    )


def _page_info(data):
    if not isinstance(data, dict):
        return {}
    page_info = data.get("page_info") or data.get("pageInfo") or {}
    return page_info if isinstance(page_info, dict) else {}


def _normaliser_campagne_tiktok(item):
    if not isinstance(item, dict):
        return None

    try:
        campaign_id = normaliser_campaign_id_tiktok(
            item.get("campaign_id")
        )
    except ValueError:
        return None

    statut = (
        item.get("operation_status")
        or item.get("secondary_status")
        or item.get("status")
        or ""
    )

    return {
        "campaign_id": campaign_id,
        "nom": (
            str(item.get("campaign_name") or "").strip()
            or f"Campagne TikTok Ads {campaign_id}"
        ),
        "statut": str(statut or "").strip(),
        "objective_type": str(
            item.get("objective_type") or ""
        ).strip(),
        "raw": item,
    }


def lister_campagnes_tiktok(access_token, advertiser_id):
    advertiser_id = normaliser_advertiser_id(advertiser_id)
    campagnes = []
    deja_vus = set()
    page = 1
    page_size = 100

    while True:
        data = _request_json_tiktok(
            "/campaign/get/",
            access_token=access_token,
            params={
                "advertiser_id": advertiser_id,
                "page": page,
                "page_size": page_size,
                "fields": CAMPAIGN_FIELDS,
                "exclude_field_types_in_response": ["NULL_FIELD"],
            },
        )

        items = _liste_depuis_data(data)
        for item in items:
            campagne = _normaliser_campagne_tiktok(item)
            if campagne is None:
                continue
            if campagne["campaign_id"] in deja_vus:
                continue
            deja_vus.add(campagne["campaign_id"])
            campagnes.append(campagne)

        page_info = _page_info(data)
        total_page = page_info.get("total_page")
        if total_page:
            try:
                total_page = int(total_page)
            except (TypeError, ValueError):
                total_page = page
            if page >= total_page:
                break
        elif len(items) < page_size:
            break
        page += 1

    return campagnes


def plage_dates_tiktok(periode):
    if periode not in PERIODES_TIKTOK_ADS:
        raise ValueError("Période TikTok Ads non autorisée.")

    aujourd_hui = timezone.localdate()
    if periode == "YESTERDAY":
        jour = aujourd_hui - timedelta(days=1)
        return jour, jour

    return (
        aujourd_hui - timedelta(days=PERIODES_TIKTOK_ADS[periode]),
        aujourd_hui,
    )


def lister_performances_campagnes_tiktok(
    access_token,
    advertiser_id,
    *,
    date_debut=None,
    date_fin=None,
    periode="LAST_30_DAYS",
):
    advertiser_id = normaliser_advertiser_id(advertiser_id)

    if date_debut is None or date_fin is None:
        date_debut, date_fin = plage_dates_tiktok(periode)

    if not isinstance(date_debut, date) or not isinstance(date_fin, date):
        raise ValueError("La plage de dates TikTok Ads est invalide.")

    if date_debut > date_fin:
        raise ValueError("La date de début TikTok Ads dépasse la date de fin.")

    lignes = []
    page = 1
    page_size = 1000

    while True:
        data = _request_json_tiktok(
            "/report/integrated/get/",
            access_token=access_token,
            params={
                "report_type": "BASIC",
                "advertiser_id": advertiser_id,
                "data_level": "AUCTION_CAMPAIGN",
                "dimensions": REPORT_DIMENSIONS,
                "metrics": REPORT_METRICS,
                "start_date": date_debut.isoformat(),
                "end_date": date_fin.isoformat(),
                "page": page,
                "page_size": page_size,
            },
        )

        items = _liste_depuis_data(data)
        lignes.extend(
            item
            for item in items
            if isinstance(item, dict)
        )

        page_info = _page_info(data)
        total_page = page_info.get("total_page")
        if total_page:
            try:
                total_page = int(total_page)
            except (TypeError, ValueError):
                total_page = page
            if page >= total_page:
                break
        elif len(items) < page_size:
            break
        page += 1

    return lignes


def rafraichir_access_token_tiktok(refresh_token):
    configuration = _configuration_tiktok_ads()
    if not refresh_token:
        raise TikTokAdsAPIError(
            "Jeton d'actualisation TikTok Ads manquant."
        )

    data = _request_json_tiktok(
        "/tt_user/oauth2/refresh_token/",
        method="POST",
        payload={
            "client_id": configuration["client_id"],
            "client_secret": configuration["client_secret"],
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
    )

    access_token = data.get("access_token") if isinstance(data, dict) else ""
    if not access_token:
        raise TikTokAdsAPIError(
            "TikTok n'a pas renvoyé de nouveau jeton d'accès."
        )

    return data


def access_token_pour_compte_tiktok(compte):
    if compte.plateforme != "tiktok_ads":
        raise ValueError(
            "Ce compte n'est pas un connecteur TikTok Ads."
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
            "Le jeton TikTok Ads est expiré. Relancez la connexion du compte."
        )

    payload = rafraichir_access_token_tiktok(refresh_token)
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
