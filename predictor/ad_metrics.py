from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re

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
    recalculer=True,
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

    devise = str(devise or "EUR").strip().upper()

    if not re.fullmatch(r"[A-Z]{3}", devise):
        raise ValueError(
            "La devise publicitaire doit être un code ISO à 3 lettres."
        )

    devises_existantes = set(
        campagne.mesures_journalieres
        .exclude(devise="")
        .values_list("devise", flat=True)
        .distinct()
    )

    if devises_existantes and devises_existantes != {devise}:
        raise ValueError(
            "Les mesures d'une même campagne publicitaire doivent utiliser une seule devise."
        )

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

    if recalculer:
        recalculer_totaux_campagne(campagne)

    return mesure


def recalculer_totaux_campagne(campagne):
    mesures = campagne.mesures_journalieres.all()

    devises = set(
        mesures
        .exclude(devise="")
        .values_list("devise", flat=True)
        .distinct()
    )

    if len(devises) > 1:
        raise ValueError(
            "Impossible d'additionner des dépenses publicitaires de devises différentes."
        )

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
    campagne.conversions = Decimal(
        totaux["conversions"] or 0
    ).quantize(Decimal("0.0001"))
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
