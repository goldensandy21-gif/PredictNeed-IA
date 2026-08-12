from __future__ import annotations

import secrets

from django.utils import timezone

from .external_connectors import calculer_expiration, get_fournisseur, signer_token
from .models import CompteConnecteExterne


SELECTION_FLOW_TTL_SECONDS = 15 * 60


def flow_session_key(plateforme):
    return f"{plateforme}_oauth_flows"


def _created_at(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _flows_valides(flows, now_ts):
    flows_valides = {}

    for key, value in dict(flows or {}).items():
        if not isinstance(value, dict):
            continue

        created_at = _created_at(value.get("created_at"))
        if created_at is None:
            continue

        age = now_ts - created_at
        if 0 <= age <= SELECTION_FLOW_TTL_SECONDS:
            flows_valides[key] = value

    return flows_valides


def creer_flux_selection_compte(
    request,
    plateforme,
    *,
    client,
    site,
    access_token,
    refresh_token,
    token_payload,
    comptes,
):
    flow_id = secrets.token_urlsafe(24)
    key = flow_session_key(plateforme)
    now_ts = timezone.now().timestamp()
    flows = _flows_valides(
        request.session.get(key, {}),
        now_ts,
    )

    flows[flow_id] = {
        "user_id": request.user.id,
        "client_id": client.id,
        "site_id": site.id,
        "created_at": now_ts,
        "access_token_signe": signer_token(access_token),
        "refresh_token_signe": signer_token(refresh_token),
        "token_type": token_payload.get("token_type", "Bearer"),
        "expires_in": token_payload.get("expires_in"),
        "oauth_user_id": str(
            token_payload.get("oauth_user_id") or ""
        ).strip(),
        "comptes": comptes,
    }

    request.session[key] = flows
    request.session.modified = True
    return flow_id


def charger_flux_selection_compte(
    request,
    plateforme,
    flow_id,
    client,
):
    key = flow_session_key(plateforme)
    flows = dict(request.session.get(key, {}))
    pending = flows.get(flow_id)

    if not flow_id or not isinstance(pending, dict) or client is None:
        return {
            "ok": False,
            "flows": flows,
            "pending": None,
            "site": None,
        }

    created_at = _created_at(pending.get("created_at"))
    age = (
        timezone.now().timestamp() - created_at
        if created_at is not None
        else None
    )

    if (
        age is None
        or age < 0
        or age > SELECTION_FLOW_TTL_SECONDS
        or pending.get("user_id") != request.user.id
        or pending.get("client_id") != client.id
    ):
        supprimer_flux_selection_compte(
            request,
            plateforme,
            flow_id,
            flows=flows,
        )
        return {
            "ok": False,
            "flows": flows,
            "pending": None,
            "site": None,
        }

    site = (
        client.sites
        .filter(
            pk=pending.get("site_id"),
            module_connecteurs_actif=True,
        )
        .first()
    )

    if site is None:
        supprimer_flux_selection_compte(
            request,
            plateforme,
            flow_id,
            flows=flows,
        )
        return {
            "ok": False,
            "flows": flows,
            "pending": None,
            "site": None,
        }

    return {
        "ok": True,
        "flows": flows,
        "pending": pending,
        "site": site,
    }


def supprimer_flux_selection_compte(
    request,
    plateforme,
    flow_id,
    *,
    flows=None,
):
    key = flow_session_key(plateforme)
    flows = dict(
        request.session.get(key, {})
        if flows is None
        else flows
    )
    flows.pop(flow_id, None)
    request.session[key] = flows
    request.session.modified = True


def compte_selectionne_existant(
    *,
    client,
    site,
    plateforme,
    identifiant_externe,
):
    return (
        CompteConnecteExterne.objects
        .filter(
            client=client,
            site=site,
            plateforme=plateforme,
            identifiant_externe=identifiant_externe,
        )
        .first()
    )


def upsert_compte_selectionne(
    *,
    client,
    site,
    plateforme,
    identifiant_externe,
    nom_compte,
    pending,
    configuration,
    dernier_message,
):
    existing = compte_selectionne_existant(
        client=client,
        site=site,
        plateforme=plateforme,
        identifiant_externe=identifiant_externe,
    )
    refresh_token_signe = (
        pending.get("refresh_token_signe")
        or (
            existing.refresh_token_signe
            if existing is not None
            else ""
        )
    )

    compte, created = CompteConnecteExterne.objects.update_or_create(
        client=client,
        site=site,
        plateforme=plateforme,
        identifiant_externe=identifiant_externe,
        defaults={
            "nom_compte": nom_compte,
            "statut": "connecte",
            "scopes": " ".join(
                get_fournisseur(plateforme).get("scopes", [])
            ),
            "access_token_signe": pending.get(
                "access_token_signe",
                "",
            ),
            "refresh_token_signe": refresh_token_signe,
            "token_type": pending.get(
                "token_type",
                "Bearer",
            ),
            "expires_at": calculer_expiration({
                "expires_in": pending.get("expires_in"),
            }),
            "configuration": configuration,
            "dernier_message": dernier_message,
        },
    )
    return compte, created
