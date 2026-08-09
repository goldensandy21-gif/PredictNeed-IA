from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from .ad_metrics import enregistrer_mesure_campagne_native
from .google_ads_api import (
    access_token_pour_compte,
    lister_performances_campagnes,
    normaliser_customer_id,
)
from .models import CampagneExterne, JournalSynchronisationConnecteur


def _decimal(value, default="0"):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _entier(value):
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _depense_depuis_micros(value):
    micros = _decimal(value)
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
    devise = (configuration.get("devise") or "EUR").strip().upper()[:12] or "EUR"
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

            conversions = _decimal(metrics.get("conversions"))
            if conversions < 0:
                conversions = Decimal("0")

            enregistrer_mesure_campagne_native(
                campagne,
                date=jour,
                impressions=_entier(metrics.get("impressions")),
                clics=_entier(metrics.get("clicks")),
                conversions=conversions,
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

        compte.derniere_synchro = maintenant
        compte.dernier_message = (
            f"{len(campagnes_ids)} campagne(s) Google Ads et "
            f"{mesures_total} mesure(s) journalière(s) synchronisées sur {periode}."
        )
        compte.save(update_fields=["derniere_synchro", "dernier_message", "date_mise_a_jour"])

        JournalSynchronisationConnecteur.objects.create(
            compte=compte,
            statut="succes",
            message=compte.dernier_message,
            details={
                "source": "google_ads_api",
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
