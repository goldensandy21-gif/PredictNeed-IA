from __future__ import annotations

from decimal import Decimal, InvalidOperation

from .models import JournalSynchronisationConnecteur


def decimal_depuis(value, default="0"):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def decimal_non_negatif(value):
    nombre = decimal_depuis(value)
    if nombre < 0:
        return Decimal("0")
    return nombre


def entier_non_negatif(value):
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def devise_depuis_configuration(compte, default="EUR"):
    configuration = dict(compte.configuration or {})
    return (
        str(configuration.get("devise") or default)
        .strip()
        .upper()[:12]
        or default
    )


def finaliser_synchronisation_native(
    compte,
    *,
    label,
    source,
    periode,
    campagnes,
    mesures,
    maintenant,
):
    compte.derniere_synchro = maintenant
    compte.dernier_message = (
        f"{campagnes} campagne(s) {label} et "
        f"{mesures} mesure(s) journalière(s) synchronisées sur {periode}."
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
            "source": source,
            "periode": periode,
            "campagnes": campagnes,
            "mesures": mesures,
        },
    )

    return compte.dernier_message
