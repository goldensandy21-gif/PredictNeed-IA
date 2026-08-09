from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db.models import Sum
from django.utils import timezone

from .models import MesureCampagneExterne


def _decimal_non_negatif(value, *, decimal_places=2):
    try:
        nombre = Decimal(str(value or "0"))
    except (InvalidOperation, TypeError, ValueError):
        nombre = Decimal("0")

    if nombre < 0:
        nombre = Decimal("0")

    quant = Decimal("1").scaleb(-decimal_places)
    return nombre.quantize(quant)


def _entier_non_negatif(value):
    try:
        nombre = int(value or 0)
    except (TypeError, ValueError):
        nombre = 0
    return max(nombre, 0)


def enregistrer_mesure_campagne_native(
    campagne,
    *,
    date,
    impressions=0,
    clics=0,
    conversions=0,
    depense=0,
    devise="EUR",
    donnees_brutes=None,
):
    if campagne.site_id is None:
        raise ValueError(
            "Une campagne native doit être rattachée à un site."
        )

    if campagne.compte.site_id != campagne.site_id:
        raise ValueError(
            "Le compte publicitaire et la campagne doivent appartenir au même site."
        )

    if campagne.compte.plateforme != campagne.plateforme:
        raise ValueError(
            "La plateforme du compte et de la campagne doit être identique."
        )

    devise = str(devise or "EUR").strip().upper()[:12] or "EUR"

    mesure, _ = MesureCampagneExterne.objects.update_or_create(
        campagne=campagne,
        date=date,
        defaults={
            "compte": campagne.compte,
            "site": campagne.site,
            "plateforme": campagne.plateforme,
            "impressions": _entier_non_negatif(impressions),
            "clics": _entier_non_negatif(clics),
            "conversions": _decimal_non_negatif(
                conversions,
                decimal_places=4,
            ),
            "depense": _decimal_non_negatif(
                depense,
                decimal_places=2,
            ),
            "devise": devise,
            "donnees_brutes": dict(donnees_brutes or {}),
        },
    )

    recalculer_totaux_campagne(campagne)
    return mesure


def recalculer_totaux_campagne(campagne):
    mesures = campagne.mesures_journalieres.all()

    totaux = mesures.aggregate(
        impressions=Sum("impressions"),
        clics=Sum("clics"),
        conversions=Sum("conversions"),
        depense=Sum("depense"),
    )

    derniere_mesure = mesures.order_by("-date").first()
    donnees_brutes = dict(campagne.donnees_brutes or {})
    donnees_brutes["origine"] = "api_regie"
    donnees_brutes["jours_mesures"] = mesures.count()

    campagne.source_donnees = "api_regie"
    campagne.impressions = int(totaux["impressions"] or 0)
    campagne.clics = int(totaux["clics"] or 0)
    campagne.conversions = int(
        Decimal(totaux["conversions"] or 0)
    )
    campagne.depense = Decimal(totaux["depense"] or 0)

    if derniere_mesure is not None:
        campagne.devise = derniere_mesure.devise

    campagne.donnees_brutes = donnees_brutes
    campagne.derniere_synchro = timezone.now()
    campagne.save(
        update_fields=[
            "source_donnees",
            "impressions",
            "clics",
            "conversions",
            "depense",
            "devise",
            "donnees_brutes",
            "derniere_synchro",
            "date_mise_a_jour",
        ]
    )
    return campagne
