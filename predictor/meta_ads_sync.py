from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .ad_metrics import enregistrer_mesure_campagne_native
from .ad_sync_utils import (
    decimal_non_negatif,
    devise_depuis_configuration,
    entier_non_negatif,
    finaliser_synchronisation_native,
)
from .external_connectors import lire_token_signe
from .meta_ads_api import (
    _extraire_conversions_meta,
    lister_performances_campagnes_meta,
    normaliser_account_id_meta,
)
from .models import CampagneExterne


def _devise_depuis_ligne(row, compte):
    devise = str(row.get("account_currency") or "").strip().upper()

    if devise:
        return devise[:12]

    return devise_depuis_configuration(compte)


def access_token_pour_compte_meta(compte):
    if compte.expires_at and compte.expires_at <= timezone.now():
        raise ValueError(
            "Le jeton Meta Ads est expiré. Relancez la connexion du compte."
        )

    access_token = lire_token_signe(compte.access_token_signe)

    if not access_token:
        raise ValueError(
            "Le jeton d'accès Meta Ads est manquant."
        )

    return access_token


def synchroniser_compte_meta_ads(compte, *, periode="LAST_30_DAYS"):
    if compte.plateforme != "meta_ads":
        raise ValueError("Ce compte n'est pas un compte Meta Ads.")
    if compte.site_id is None:
        raise ValueError("Le compte Meta Ads doit être rattaché à un site.")
    if not compte.identifiant_externe:
        raise ValueError("L'account_id Meta Ads est manquant.")

    account_id = normaliser_account_id_meta(
        compte.identifiant_externe
    )
    access_token = access_token_pour_compte_meta(compte)

    rows = lister_performances_campagnes_meta(
        access_token,
        account_id,
        periode=periode,
    )

    campagnes_ids = set()
    mesures_total = 0
    maintenant = timezone.now()

    with transaction.atomic():
        for row in rows:
            campaign_id = str(row.get("campaign_id") or "").strip()
            date_raw = str(row.get("date_start") or "").strip()

            if not campaign_id or not date_raw:
                continue

            try:
                jour = date.fromisoformat(date_raw)
            except ValueError:
                continue

            nom = (
                str(row.get("campaign_name") or "").strip()
                or f"Campagne Meta Ads {campaign_id}"
            )
            devise = _devise_depuis_ligne(row, compte)

            campagne, _ = CampagneExterne.objects.update_or_create(
                compte=compte,
                identifiant_externe=campaign_id,
                defaults={
                    "site": compte.site,
                    "plateforme": "meta_ads",
                    "source_donnees": "api_regie",
                    "nom": nom[:220],
                    "statut": "",
                    "utm_source": "",
                    "utm_medium": "",
                    "utm_campaign": "",
                    "devise": devise,
                    "donnees_brutes": {
                        "origine": "api_regie",
                        "provider": "meta_ads",
                        "account_id": account_id,
                        "campaign_id": campaign_id,
                    },
                    "derniere_synchro": maintenant,
                },
            )

            conversions = _extraire_conversions_meta(row)

            enregistrer_mesure_campagne_native(
                campagne,
                date=jour,
                impressions=entier_non_negatif(
                    row.get("impressions")
                ),
                clics=entier_non_negatif(row.get("clicks")),
                conversions=conversions,
                depense=decimal_non_negatif(row.get("spend")).quantize(
                    Decimal("0.01")
                ),
                devise=devise,
                donnees_brutes={
                    "provider": "meta_ads",
                    "account_id": account_id,
                    "campaign_id": campaign_id,
                    "date_stop": row.get("date_stop") or "",
                    "actions": row.get("actions") or [],
                    "conversions": row.get("conversions") or [],
                },
            )

            campagnes_ids.add(campagne.id)
            mesures_total += 1

        finaliser_synchronisation_native(
            compte=compte,
            label="Meta Ads",
            source="meta_ads_api",
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
