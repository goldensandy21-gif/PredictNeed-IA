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
    lister_campagnes_google_ads,
    lister_performances_campagnes,
    normaliser_customer_id,
)
from .models import CampagneExterne


def _depense_depuis_micros(value):
    micros = decimal_depuis(value)

    if micros < 0:
        micros = Decimal("0")

    return (
        micros / Decimal("1000000")
    ).quantize(Decimal("0.01"))


def _donnees_campagne_google(
    *,
    campaign,
    budget,
    customer_id,
):
    budget_micros = budget.get("amountMicros")
    budget_total_micros = budget.get("totalAmountMicros")

    return {
        "origine": "api_regie",
        "provider": "google_ads",
        "customer_id": customer_id,
        "campaign_id": str(campaign.get("id") or ""),
        "status": campaign.get("status") or "",
        "primary_status": campaign.get("primaryStatus") or "",
        "serving_status": campaign.get("servingStatus") or "",
        "advertising_channel_type": (
            campaign.get("advertisingChannelType") or ""
        ),
        "advertising_channel_sub_type": (
            campaign.get("advertisingChannelSubType") or ""
        ),
        "start_date_time": campaign.get("startDateTime") or "",
        "end_date_time": campaign.get("endDateTime") or "",
        "optimization_score": campaign.get("optimizationScore"),
        "bidding_strategy_type": (
            campaign.get("biddingStrategyType") or ""
        ),
        "bidding_strategy_system_status": (
            campaign.get("biddingStrategySystemStatus") or ""
        ),
        "budget_status": budget.get("status") or "",
        "budget_amount_micros": (
            str(budget_micros)
            if budget_micros is not None
            else ""
        ),
        "budget_amount": (
            str(_depense_depuis_micros(budget_micros))
            if budget_micros is not None
            else ""
        ),
        "budget_total_amount_micros": (
            str(budget_total_micros)
            if budget_total_micros is not None
            else ""
        ),
        "budget_total_amount": (
            str(_depense_depuis_micros(budget_total_micros))
            if budget_total_micros is not None
            else ""
        ),
    }


def _upsert_campagne_google(
    *,
    compte,
    customer_id,
    campaign,
    budget,
    devise,
    maintenant,
):
    campaign_id = str(campaign.get("id") or "").strip()

    if not campaign_id or not campaign_id.isdigit():
        return None

    nom = (
        str(campaign.get("name") or "").strip()
        or f"Campagne Google Ads {campaign_id}"
    )

    campagne, _ = CampagneExterne.objects.update_or_create(
        compte=compte,
        identifiant_externe=campaign_id,
        defaults={
            "site": compte.site,
            "plateforme": "google_ads",
            "source_donnees": "api_regie",
            "nom": nom[:220],
            "statut": str(
                campaign.get("status") or ""
            )[:80],
            "utm_source": "",
            "utm_medium": "",
            "utm_campaign": "",
            "devise": devise,
            "donnees_brutes": _donnees_campagne_google(
                campaign=campaign,
                budget=budget,
                customer_id=customer_id,
            ),
            "derniere_synchro": maintenant,
        },
    )

    return campagne


def synchroniser_compte_google_ads(
    compte,
    *,
    periode="LAST_30_DAYS",
):
    if compte.plateforme != "google_ads":
        raise ValueError(
            "Ce compte n'est pas un compte Google Ads."
        )

    if compte.site_id is None:
        raise ValueError(
            "Le compte Google Ads doit être rattaché à un site."
        )

    if not compte.identifiant_externe:
        raise ValueError(
            "Le customer_id Google Ads est manquant."
        )

    customer_id = normaliser_customer_id(
        compte.identifiant_externe
    )

    configuration = dict(compte.configuration or {})

    login_customer_id = (
        configuration.get("login_customer_id") or ""
    )

    devise = devise_depuis_configuration(compte)

    access_token = access_token_pour_compte(compte)

    maintenant = timezone.now()

    # --------------------------------------------------------
    # 1. INVENTAIRE DES CAMPAGNES
    #
    # Cette requête est indépendante des métriques.
    # Une campagne sans impression/clic/conversion reste visible.
    # Les anciennes campagnes REMOVED restent également connues.
    # --------------------------------------------------------

    campagnes_google = lister_campagnes_google_ads(
        access_token,
        customer_id,
        login_customer_id=login_customer_id,
    )

    campagnes_par_id = {}
    campagnes_ids = set()

    with transaction.atomic():

        for row in campagnes_google:
            campaign = row.get("campaign") or {}
            budget = row.get("campaignBudget") or {}

            campagne = _upsert_campagne_google(
                compte=compte,
                customer_id=customer_id,
                campaign=campaign,
                budget=budget,
                devise=devise,
                maintenant=maintenant,
            )

            if campagne is None:
                continue

            campagnes_par_id[
                campagne.identifiant_externe
            ] = campagne

            campagnes_ids.add(campagne.id)

        # ----------------------------------------------------
        # 2. PERFORMANCES JOURNALIÈRES
        #
        # Une absence de ligne ici signifie simplement :
        # aucune métrique disponible pour cette période.
        # Elle ne signifie plus "aucune campagne".
        # ----------------------------------------------------

        rows = lister_performances_campagnes(
            access_token,
            customer_id,
            login_customer_id=login_customer_id,
            periode=periode,
        )

        mesures_total = 0

        for row in rows:
            campaign = row.get("campaign") or {}
            segments = row.get("segments") or {}
            metrics = row.get("metrics") or {}

            campaign_id = str(
                campaign.get("id") or ""
            ).strip()

            date_raw = str(
                segments.get("date") or ""
            ).strip()

            if (
                not campaign_id
                or not campaign_id.isdigit()
                or not date_raw
            ):
                continue

            try:
                jour = date.fromisoformat(date_raw)
            except ValueError:
                continue

            campagne = campagnes_par_id.get(campaign_id)

            if campagne is None:
                campagne = _upsert_campagne_google(
                    compte=compte,
                    customer_id=customer_id,
                    campaign=campaign,
                    budget={},
                    devise=devise,
                    maintenant=maintenant,
                )

                if campagne is None:
                    continue

                campagnes_par_id[campaign_id] = campagne
                campagnes_ids.add(campagne.id)

            enregistrer_mesure_campagne_native(
                campagne,
                date=jour,
                impressions=entier_non_negatif(
                    metrics.get("impressions")
                ),
                clics=entier_non_negatif(
                    metrics.get("clicks")
                ),
                conversions=decimal_non_negatif(
                    metrics.get("conversions")
                ),
                depense=_depense_depuis_micros(
                    metrics.get("costMicros")
                ),
                devise=devise,
                donnees_brutes={
                    "provider": "google_ads",
                    "customer_id": customer_id,
                    "campaign_id": campaign_id,
                    "campaign_status": (
                        campaign.get("status") or ""
                    ),
                    "advertising_channel_type": (
                        campaign.get(
                            "advertisingChannelType"
                        ) or ""
                    ),
                    "impressions": str(
                        metrics.get("impressions") or "0"
                    ),
                    "clicks": str(
                        metrics.get("clicks") or "0"
                    ),
                    "ctr": str(
                        metrics.get("ctr") or "0"
                    ),
                    "average_cpc": str(
                        metrics.get("averageCpc") or "0"
                    ),
                    "conversions": str(
                        metrics.get("conversions") or "0"
                    ),
                    "conversions_value": str(
                        metrics.get(
                            "conversionsValue"
                        ) or "0"
                    ),
                    "all_conversions": str(
                        metrics.get(
                            "allConversions"
                        ) or "0"
                    ),
                    "all_conversions_value": str(
                        metrics.get(
                            "allConversionsValue"
                        ) or "0"
                    ),
                    "cost_per_conversion": str(
                        metrics.get(
                            "costPerConversion"
                        ) or "0"
                    ),
                    "cost_micros": str(
                        metrics.get("costMicros") or "0"
                    ),
                },
            )

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
