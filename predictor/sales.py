from decimal import Decimal, InvalidOperation
import re

from django.db.models import Sum
from django.utils import timezone

from .attribution import appliquer_attribution_opportunite
from .models import Vente


def enregistrer_vente_opportunite(
    opportunite,
    *,
    montant,
    devise="EUR",
    date_vente=None,
    reference_vente="",
):
    try:
        montant = Decimal(montant).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(
            "Le montant réellement vendu doit être un nombre valide."
        ) from exc

    if not montant.is_finite():
        raise ValueError(
            "Le montant réellement vendu doit être un nombre fini."
        )

    if montant <= 0:
        raise ValueError(
            "Le montant réellement vendu doit être supérieur à zéro."
        )

    if montant > Decimal("9999999999.99"):
        raise ValueError(
            "Le montant réellement vendu dépasse la capacité enregistrable."
        )

    appliquer_attribution_opportunite(opportunite)

    devise = str(devise or "EUR").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", devise):
        raise ValueError(
            "La devise doit être un code ISO à 3 lettres, par exemple EUR ou USD."
        )

    reference = str(reference_vente or "").strip()[:120] or None

    if reference and (
        Vente.objects
        .filter(site=opportunite.site, reference_vente=reference)
        .exclude(opportunite=opportunite)
        .exists()
    ):
        raise ValueError(
            "Cette référence de vente existe déjà pour ce site."
        )

    lead = opportunite.lead
    session = getattr(lead, "session", None) if lead else None

    if lead and lead.site_id != opportunite.site_id:
        lead = None
        session = None

    if session and session.site_id != opportunite.site_id:
        session = None

    vente, _ = Vente.objects.update_or_create(
        opportunite=opportunite,
        defaults={
            "site": opportunite.site,
            "lead": lead,
            "session": session,
            "montant": montant,
            "devise": devise,
            "date_vente": date_vente or timezone.localdate(),
            "reference_vente": reference,
            "statut": "confirmee",
            "source_attribution": opportunite.source_attribution,
            "utm_source_attribution": opportunite.utm_source_attribution,
            "utm_medium_attribution": opportunite.utm_medium_attribution,
            "utm_campaign_attribution": opportunite.utm_campaign_attribution,
            "details_attribution": dict(
                opportunite.details_attribution or {}
            ),
        },
    )
    return vente


def annuler_vente_opportunite(opportunite):
    vente = Vente.objects.filter(opportunite=opportunite).first()

    if vente and vente.statut == "confirmee":
        vente.statut = "annulee"
        vente.save(update_fields=["statut", "date_mise_a_jour"])

    return vente

def agreger_montants_par_devise(queryset):
    resultats = []

    for ligne in (
        queryset
        .values("devise")
        .annotate(total=Sum("montant"))
        .order_by("devise")
    ):
        devise = str(ligne.get("devise") or "").strip().upper()
        total = ligne.get("total") or Decimal("0")

        if not re.fullmatch(r"[A-Z]{3}", devise):
            continue

        resultats.append({
            "devise": devise,
            "total": total,
        })

    return resultats
