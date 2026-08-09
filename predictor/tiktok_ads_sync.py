from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from .ad_metrics import enregistrer_mesure_campagne_native
from .models import CampagneExterne, JournalSynchronisationConnecteur
from .tiktok_ads_api import (
    access_token_pour_compte_tiktok,
    lister_campagnes_tiktok,
    lister_performances_campagnes_tiktok,
    normaliser_advertiser_id,
    normaliser_campaign_id_tiktok,
)


def _decimal(value, default="0"):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _decimal_non_negatif(value):
    nombre = _decimal(value)
    if nombre < 0:
        return Decimal("0")
    return nombre


def _entier(value):
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _devise_compte(compte):
    configuration = dict(compte.configuration or {})
    return (
        str(configuration.get("devise") or "EUR")
        .strip()
        .upper()[:12]
        or "EUR"
    )


def _campaign_id_depuis_ligne(row):
    dimensions = row.get("dimensions")
    if isinstance(dimensions, dict):
        value = dimensions.get("campaign_id")
    else:
        value = (
            row.get("campaign_id")
            or row.get("campaignId")
        )

    try:
        return normaliser_campaign_id_tiktok(value)
    except ValueError:
        return ""


def _date_depuis_ligne(row):
    dimensions = row.get("dimensions")
    if isinstance(dimensions, dict):
        value = dimensions.get("stat_time_day")
    else:
        value = row.get("stat_time_day") or row.get("date")

    value = str(value or "").strip()
    if not value:
        return None

    value = value.split(" ", 1)[0]
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _metrics(row):
    metrics = row.get("metrics")
    return metrics if isinstance(metrics, dict) else row


def synchroniser_compte_tiktok_ads(compte, *, periode="LAST_30_DAYS"):
    if compte.plateforme != "tiktok_ads":
        raise ValueError("Ce compte n'est pas un compte TikTok Ads.")
    if compte.site_id is None:
        raise ValueError("Le compte TikTok Ads doit être rattaché à un site.")
    if not compte.identifiant_externe:
        raise ValueError("L'advertiser_id TikTok Ads est manquant.")

    advertiser_id = normaliser_advertiser_id(
        compte.identifiant_externe
    )
    devise = _devise_compte(compte)
    access_token = access_token_pour_compte_tiktok(compte)

    campagnes = {
        campagne["campaign_id"]: campagne
        for campagne in lister_campagnes_tiktok(
            access_token,
            advertiser_id,
        )
    }
    rows = lister_performances_campagnes_tiktok(
        access_token,
        advertiser_id,
        periode=periode,
    )

    campagnes_ids = set()
    mesures_total = 0
    maintenant = timezone.now()

    with transaction.atomic():
        for row in rows:
            campaign_id = _campaign_id_depuis_ligne(row)
            jour = _date_depuis_ligne(row)

            if not campaign_id or jour is None:
                continue

            metrics = _metrics(row)
            campagne_data = campagnes.get(campaign_id, {})
            nom = (
                campagne_data.get("nom")
                or f"Campagne TikTok Ads {campaign_id}"
            )

            campagne, _ = CampagneExterne.objects.update_or_create(
                compte=compte,
                identifiant_externe=campaign_id,
                defaults={
                    "site": compte.site,
                    "plateforme": "tiktok_ads",
                    "source_donnees": "api_regie",
                    "nom": nom[:220],
                    "statut": str(
                        campagne_data.get("statut") or ""
                    )[:80],
                    "utm_source": "",
                    "utm_medium": "",
                    "utm_campaign": "",
                    "devise": devise,
                    "donnees_brutes": {
                        "origine": "api_regie",
                        "provider": "tiktok_ads",
                        "advertiser_id": advertiser_id,
                        "campaign_id": campaign_id,
                        "objective_type": (
                            campagne_data.get("objective_type") or ""
                        ),
                    },
                    "derniere_synchro": maintenant,
                },
            )

            enregistrer_mesure_campagne_native(
                campagne,
                date=jour,
                impressions=_entier(metrics.get("impressions")),
                clics=_entier(metrics.get("clicks")),
                conversions=_decimal_non_negatif(
                    metrics.get("conversion")
                    or metrics.get("conversions")
                ),
                depense=_decimal_non_negatif(
                    metrics.get("spend")
                ).quantize(Decimal("0.01")),
                devise=devise,
                donnees_brutes={
                    "provider": "tiktok_ads",
                    "advertiser_id": advertiser_id,
                    "campaign_id": campaign_id,
                    "dimensions": row.get("dimensions") or {},
                    "metrics": metrics,
                },
            )

            campagnes_ids.add(campagne.id)
            mesures_total += 1

        compte.derniere_synchro = maintenant
        compte.dernier_message = (
            f"{len(campagnes_ids)} campagne(s) TikTok Ads et "
            f"{mesures_total} mesure(s) journalière(s) synchronisées sur {periode}."
        )
        compte.save(
            update_fields=[
                "derniere_synchro",
                "dernier_message",
                "date_mise_a_jour",
            ]
        )

        JournalSynchronisationConnecteur.objects.create(
            compte=compte,
            statut="succes",
            message=compte.dernier_message,
            details={
                "source": "tiktok_ads_api",
                "periode": periode,
                "campagnes": len(campagnes_ids),
                "mesures": mesures_total,
            },
        )

    return {
        "campagnes": len(campagnes_ids),
        "mesures": mesures_total,
        "periode": periode,
    }
