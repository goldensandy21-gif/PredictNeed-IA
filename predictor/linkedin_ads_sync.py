from __future__ import annotations

from datetime import date

from django.db import transaction
from django.utils import timezone

from .ad_metrics import enregistrer_mesure_campagne_native
from .ad_sync_utils import (
    decimal_non_negatif,
    devise_depuis_configuration,
    entier_non_negatif,
    finaliser_synchronisation_native,
)
from .linkedin_ads_api import (
    access_token_pour_compte_linkedin,
    extraire_depense_linkedin,
    lister_campagnes_linkedin,
    lister_performances_campagnes_linkedin,
    normaliser_sponsored_account_id,
    normaliser_sponsored_campaign_id,
)
from .models import CampagneExterne


def _date_depuis_ligne(row):
    date_range = row.get("dateRange")
    start = (
        date_range.get("start")
        if isinstance(date_range, dict)
        else None
    )

    if isinstance(start, dict):
        try:
            return date(
                int(start["year"]),
                int(start["month"]),
                int(start["day"]),
            )
        except (KeyError, TypeError, ValueError):
            return None

    date_raw = str(row.get("date") or row.get("day") or "").strip()
    if not date_raw:
        return None

    try:
        return date.fromisoformat(date_raw)
    except ValueError:
        return None


def _campaign_id_depuis_ligne(row):
    pivot_values = row.get("pivotValues")
    if isinstance(pivot_values, list):
        for value in pivot_values:
            try:
                return normaliser_sponsored_campaign_id(value)
            except ValueError:
                continue

    try:
        return normaliser_sponsored_campaign_id(
            row.get("campaign")
            or row.get("campaignId")
            or row.get("campaign_id")
        )
    except ValueError:
        return ""


def synchroniser_compte_linkedin_ads(compte, *, periode="LAST_30_DAYS"):
    if compte.plateforme != "linkedin_ads":
        raise ValueError("Ce compte n'est pas un compte LinkedIn Ads.")
    if compte.site_id is None:
        raise ValueError("Le compte LinkedIn Ads doit être rattaché à un site.")
    if not compte.identifiant_externe:
        raise ValueError("L'account_id LinkedIn Ads est manquant.")

    account_id = normaliser_sponsored_account_id(
        compte.identifiant_externe
    )
    devise_compte = devise_depuis_configuration(compte)
    access_token = access_token_pour_compte_linkedin(compte)

    campagnes = {
        campagne["campaign_id"]: campagne
        for campagne in lister_campagnes_linkedin(
            access_token,
            account_id,
        )
    }
    rows = lister_performances_campagnes_linkedin(
        access_token,
        account_id,
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

            campagne_data = campagnes.get(campaign_id, {})
            nom = (
                campagne_data.get("nom")
                or f"Campagne LinkedIn Ads {campaign_id}"
            )
            depense, devise_ligne = extraire_depense_linkedin(
                row.get("costInLocalCurrency")
            )
            devise = (devise_ligne or devise_compte)[:12] or "EUR"

            campagne, _ = CampagneExterne.objects.update_or_create(
                compte=compte,
                identifiant_externe=campaign_id,
                defaults={
                    "site": compte.site,
                    "plateforme": "linkedin_ads",
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
                        "provider": "linkedin_ads",
                        "account_id": account_id,
                        "campaign_id": campaign_id,
                        "campaign_urn": (
                            campagne_data.get("urn") or ""
                        ),
                    },
                    "derniere_synchro": maintenant,
                },
            )

            enregistrer_mesure_campagne_native(
                campagne,
                date=jour,
                impressions=entier_non_negatif(
                    row.get("impressions")
                ),
                clics=entier_non_negatif(
                    row.get("landingPageClicks")
                    or row.get("clicks")
                ),
                conversions=decimal_non_negatif(
                    row.get("externalWebsiteConversions")
                ),
                depense=depense,
                devise=devise,
                donnees_brutes={
                    "provider": "linkedin_ads",
                    "account_id": account_id,
                    "campaign_id": campaign_id,
                    "pivot_values": row.get("pivotValues") or [],
                    "cost_in_local_currency": (
                        row.get("costInLocalCurrency") or {}
                    ),
                },
            )

            campagnes_ids.add(campagne.id)
            mesures_total += 1

        finaliser_synchronisation_native(
            compte=compte,
            label="LinkedIn Ads",
            source="linkedin_ads_api",
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
