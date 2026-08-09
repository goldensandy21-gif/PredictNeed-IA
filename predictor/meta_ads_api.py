from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings


class MetaAdsConfigurationError(Exception):
    pass


class MetaAdsAPIError(Exception):
    pass


def _configuration_meta_ads():
    try:
        configuration = settings.PREDICTNEED_EXTERNAL_CONNECTORS["meta_ads"]
    except KeyError as exc:
        raise MetaAdsConfigurationError(
            "Configuration Meta Ads introuvable."
        ) from exc

    api_version = str(
        configuration.get("api_version") or "v25.0"
    ).strip()

    if not re.fullmatch(r"v\d+\.\d+", api_version):
        raise MetaAdsConfigurationError(
            "META_ADS_API_VERSION doit être au format v25.0."
        )

    return {
        "api_version": api_version,
        "base_url": f"https://graph.facebook.com/{api_version}",
    }


def _requete_graph(
    path,
    *,
    access_token,
    params=None,
):
    token = str(access_token or "").strip()

    if not token:
        raise MetaAdsConfigurationError(
            "Jeton d'accès Meta Ads manquant."
        )

    configuration = _configuration_meta_ads()
    path = "/" + str(path or "").lstrip("/")

    query = urlencode(
        {
            key: value
            for key, value in (params or {}).items()
            if value not in (None, "")
        }
    )

    url = f"{configuration['base_url']}{path}"
    if query:
        url = f"{url}?{query}"

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(
                response.read().decode("utf-8")
            )
    except HTTPError as exc:
        try:
            details = json.loads(
                exc.read().decode("utf-8")
            )
        except Exception:
            details = {"message": str(exc)}

        error_payload = details.get("error", details)
        message = (
            error_payload.get("message")
            if isinstance(error_payload, dict)
            else str(error_payload)
        )
        raise MetaAdsAPIError(
            message or "Erreur HTTP Meta Ads."
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise MetaAdsAPIError(
            f"Connexion Meta Ads impossible : {exc}"
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MetaAdsAPIError(
            "Réponse Meta Ads invalide."
        ) from exc

    if not isinstance(payload, dict):
        raise MetaAdsAPIError(
            "Réponse Meta Ads inattendue."
        )

    if payload.get("error"):
        error_payload = payload["error"]
        message = (
            error_payload.get("message")
            if isinstance(error_payload, dict)
            else str(error_payload)
        )
        raise MetaAdsAPIError(
            message or "Erreur Meta Ads."
        )

    return payload


def _normaliser_compte_meta(item):
    if not isinstance(item, dict):
        return None

    account_id = str(
        item.get("account_id") or ""
    ).strip()

    graph_id = str(
        item.get("id") or ""
    ).strip()

    if not account_id and graph_id.startswith("act_"):
        account_id = graph_id[4:]

    if not account_id:
        return None

    graph_id = graph_id or f"act_{account_id}"

    return {
        "account_id": account_id,
        "graph_id": graph_id,
        "nom": (
            str(item.get("name") or "").strip()
            or f"Meta Ads {account_id}"
        ),
        "devise": str(
            item.get("currency") or ""
        ).strip().upper(),
        "fuseau_horaire": str(
            item.get("timezone_name") or ""
        ).strip(),
        "statut_meta": item.get("account_status"),
    }


def lister_comptes_publicitaires_meta(access_token):
    comptes = []
    deja_vus = set()
    after = None

    while True:
        params = {
            "fields": (
                "id,account_id,name,currency,"
                "timezone_name,account_status"
            ),
            "limit": 100,
        }

        if after:
            params["after"] = after

        payload = _requete_graph(
            "/me/adaccounts",
            access_token=access_token,
            params=params,
        )

        data = payload.get("data", [])
        if not isinstance(data, list):
            raise MetaAdsAPIError(
                "Liste de comptes Meta Ads invalide."
            )

        for item in data:
            compte = _normaliser_compte_meta(item)
            if compte is None:
                continue

            if compte["account_id"] in deja_vus:
                continue

            deja_vus.add(compte["account_id"])
            comptes.append(compte)

        paging = payload.get("paging") or {}
        cursors = (
            paging.get("cursors")
            if isinstance(paging, dict)
            else {}
        ) or {}
        next_url = (
            paging.get("next")
            if isinstance(paging, dict)
            else None
        )

        after = (
            cursors.get("after")
            if isinstance(cursors, dict)
            and next_url
            else None
        )

        if not after:
            break

    return comptes
