from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .ad_metrics import enregistrer_mesure_campagne_native
from .ad_sync_utils import (
    decimal_depuis,
    decimal_non_negatif,
    devise_depuis_configuration,
    entier_non_negatif,
    finaliser_synchronisation_native,
)
from .google_ads_api import (
    access_token_pour_compte,
    lister_performances_campagnes,
    normaliser_customer_id,
)
from .models import CampagneExterne


def _depense_depuis_micros(value):
    micros = decimal_depuis(value)
    if micros < 0:
        micros = Decimal("0")
    return (micros / Decimal("1000000")).quantize(Decimal("0.01"))


def synchroniser_compte_google_ads(compte, *, periode="LAST_30_DAYS"):
    if compte.plateforme != "google_ads":
        raise ValueError("Ce compte n'est pas un compte Google Ads.")
    if compte.site_id is None:
        raise ValueError("Le compte Google Ads doit être rattaché à un site.")
    if not compte.identifiant_externe:
        raise ValueError("Le customer_id Google Ads est manquant.")

    customer_id = normaliser_customer_id(compte.identifiant_externe)
    configuration = dict(compte.configuration or {})
    login_customer_id = configuration.get("login_customer_id") or ""
    devise = devise_depuis_configuration(compte)
    access_token = access_token_pour_compte(compte)

    rows = lister_performances_campagnes(
        access_token,
        customer_id,
        login_customer_id=login_customer_id,
        periode=periode,
    )

    campagnes_ids = set()
    mesures_total = 0
    maintenant = timezone.now()

    with transaction.atomic():
        for row in rows:
            campaign = row.get("campaign") or {}
            segments = row.get("segments") or {}
            metrics = row.get("metrics") or {}

            campaign_id = str(campaign.get("id") or "").strip()
            date_raw = str(segments.get("date") or "").strip()
            if not campaign_id or not campaign_id.isdigit() or not date_raw:
                continue

            try:
                jour = date.fromisoformat(date_raw)
            except ValueError:
                continue

            nom = str(campaign.get("name") or "").strip() or f"Campagne Google Ads {campaign_id}"

            campagne, _ = CampagneExterne.objects.update_or_create(
                compte=compte,
                identifiant_externe=campaign_id,
                defaults={
                    "site": compte.site,
                    "plateforme": "google_ads",
                    "source_donnees": "api_regie",
                    "nom": nom[:220],
                    "statut": str(campaign.get("status") or "")[:80],
                    "utm_source": "",
                    "utm_medium": "",
                    "utm_campaign": "",
                    "devise": devise,
                    "donnees_brutes": {
                        "origine": "api_regie",
                        "provider": "google_ads",
                        "customer_id": customer_id,
                        "campaign_id": campaign_id,
                        "advertising_channel_type": campaign.get("advertisingChannelType") or "",
                    },
                    "derniere_synchro": maintenant,
                },
            )

            enregistrer_mesure_campagne_native(
                campagne,
                date=jour,
                impressions=entier_non_negatif(
                    metrics.get("impressions")
                ),
                clics=entier_non_negatif(metrics.get("clicks")),
                conversions=decimal_non_negatif(
                    metrics.get("conversions")
                ),
                depense=_depense_depuis_micros(metrics.get("costMicros")),
                devise=devise,
                donnees_brutes={
                    "provider": "google_ads",
                    "customer_id": customer_id,
                    "campaign_id": campaign_id,
                    "campaign_status": campaign.get("status") or "",
                    "advertising_channel_type": campaign.get("advertisingChannelType") or "",
                    "cost_micros": str(metrics.get("costMicros") or "0"),
                },
            )

            campagnes_ids.add(campagne.id)
            mesures_total += 1

        finaliser_synchronisation_native(
            compte=compte,
            label="Google Ads",
            source="google_ads_api",
            periode=periode,
            campagnes=len(campagnes_ids),
            mesures=mesures_total,
            maintenant=maintenant,
        )

    return {
        "campagnes": len(campagnes_ids),
        "mesures": mesures_total,
        "periode": periode,
    }
