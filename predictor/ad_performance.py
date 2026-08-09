from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db.models import Sum

from .models import SessionVisiteur, Vente


def _decimal(value):
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _money(value):
    return _decimal(value).quantize(Decimal("0.01"))


def _ratio(value):
    return _decimal(value).quantize(Decimal("0.01"))


def _percent(value):
    return _decimal(value).quantize(Decimal("0.1"))


def _normaliser(value):
    return str(value or "").strip().casefold()


def _queryset_dans_periode(queryset, champ, date_debut=None, date_fin=None):
    if date_debut:
        queryset = queryset.filter(**{f"{champ}__gte": date_debut})
    if date_fin:
        queryset = queryset.filter(**{f"{champ}__lte": date_fin})
    return queryset


def _vente_correspond_a_campagne(vente, campagne):
    utm_campaign_vente = _normaliser(
        vente.utm_campaign_attribution
    )
    utm_source_vente = _normaliser(
        vente.utm_source_attribution
    )
    utm_medium_vente = _normaliser(
        vente.utm_medium_attribution
    )

    campagne_utm = _normaliser(campagne.utm_campaign)
    campagne_source = _normaliser(campagne.utm_source)
    campagne_medium = _normaliser(campagne.utm_medium)
    identifiant_externe = _normaliser(
        campagne.identifiant_externe
    )

    if campagne_utm:
        if utm_campaign_vente != campagne_utm:
            return False

        if (
            campagne_source
            and utm_source_vente != campagne_source
        ):
            return False

        if (
            campagne_medium
            and utm_medium_vente != campagne_medium
        ):
            return False

        return True

    if (
        identifiant_externe
        and not identifiant_externe.startswith("utm:")
    ):
        if utm_campaign_vente == identifiant_externe:
            return True

        details = dict(vente.details_attribution or {})
        if _normaliser(details.get("utm_id")) == identifiant_externe:
            return True

    return False


def _attribution_observable(
    campagne,
    *,
    date_debut=None,
    date_fin=None,
    ventes_correspondantes=None,
):
    if campagne.utm_campaign:
        return True

    if ventes_correspondantes:
        return True

    identifiant_externe = str(
        campagne.identifiant_externe or ""
    ).strip()

    if (
        not identifiant_externe
        or identifiant_externe.startswith("utm:")
    ):
        return False

    site_id = campagne.site_id or campagne.compte.site_id
    if site_id is None:
        return False

    sessions = SessionVisiteur.objects.filter(site_id=site_id)
    sessions = _queryset_dans_periode(
        sessions,
        "date_creation__date",
        date_debut,
        date_fin,
    )

    return (
        sessions.filter(utm_id=identifiant_externe).exists()
        or sessions.filter(
            utm_campaign=identifiant_externe
        ).exists()
    )


def _recommandation(statut, roas):
    if statut == "depense_indisponible":
        return (
            "Dépense publicitaire indisponible : "
            "aucun ROAS ou ROI ne peut être calculé."
        )

    if statut == "attribution_insuffisante":
        return (
            "Attribution insuffisante : relier la campagne "
            "aux visites ou ventes avant d'interpréter sa rentabilité."
        )

    if statut == "devise_incompatible":
        return (
            "Devises incompatibles : aucun ratio financier "
            "n'est calculé sans conversion de change explicite."
        )

    if roas is None:
        return "Données insuffisantes pour recommander une action."

    if roas >= Decimal("3"):
        return (
            "Performance publicitaire forte : maintenir la campagne "
            "et tester une hausse progressive du budget."
        )

    if roas >= Decimal("1"):
        return (
            "Le chiffre d'affaires attribué couvre la dépense publicitaire : "
            "maintenir et surveiller l'évolution."
        )

    return (
        "Le chiffre d'affaires attribué est inférieur à la dépense "
        "publicitaire : optimiser avant d'augmenter le budget."
    )


def calculer_performance_campagne(
    campagne,
    *,
    date_debut=None,
    date_fin=None,
):
    site_id = campagne.site_id or campagne.compte.site_id

    mesures = campagne.mesures_journalieres.all()
    mesures = _queryset_dans_periode(
        mesures,
        "date",
        date_debut,
        date_fin,
    )

    totaux = mesures.aggregate(
        impressions=Sum("impressions"),
        clics=Sum("clics"),
        conversions=Sum("conversions"),
        depense=Sum("depense"),
    )

    a_mesures_journalieres = mesures.exists()

    if a_mesures_journalieres:
        impressions = int(totaux["impressions"] or 0)
        clics = int(totaux["clics"] or 0)
        conversions = _decimal(
            totaux["conversions"]
        ).quantize(Decimal("0.0001"))
        depense = _money(totaux["depense"])

        devises_mesures = {
            str(devise or "").strip().upper()
            for devise in mesures.values_list(
                "devise",
                flat=True,
            )
            if str(devise or "").strip()
        }

        if len(devises_mesures) > 1:
            raise ValueError(
                "Une campagne ne peut pas être analysée "
                "avec plusieurs devises publicitaires."
            )

        devise = (
            next(iter(devises_mesures))
            if devises_mesures
            else str(campagne.devise or "").strip().upper()
        )
    else:
        impressions = (
            int(campagne.impressions or 0)
            if not date_debut and not date_fin
            else 0
        )
        clics = (
            int(campagne.clics or 0)
            if not date_debut and not date_fin
            else 0
        )
        conversions = (
            _decimal(campagne.conversions).quantize(
                Decimal("0.0001")
            )
            if not date_debut and not date_fin
            else Decimal("0.0000")
        )
        depense = (
            _money(campagne.depense)
            if not date_debut and not date_fin
            else Decimal("0.00")
        )
        devise = str(
            campagne.devise or ""
        ).strip().upper()

    ventes_base = Vente.objects.filter(
        site_id=site_id,
        statut="confirmee",
    )
    ventes_base = _queryset_dans_periode(
        ventes_base,
        "date_vente",
        date_debut,
        date_fin,
    )

    ventes_correspondantes = [
        vente
        for vente in ventes_base
        if _vente_correspond_a_campagne(
            vente,
            campagne,
        )
    ]

    attribution_observable = _attribution_observable(
        campagne,
        date_debut=date_debut,
        date_fin=date_fin,
        ventes_correspondantes=ventes_correspondantes,
    )

    ventes_devise_incompatible = [
        vente
        for vente in ventes_correspondantes
        if str(vente.devise or "").strip().upper() != devise
    ]

    ventes_compatibles = [
        vente
        for vente in ventes_correspondantes
        if str(vente.devise or "").strip().upper() == devise
    ]

    chiffre_affaires_attribue = _money(
        sum(
            (vente.montant for vente in ventes_compatibles),
            Decimal("0"),
        )
    )

    roas = None
    roi_publicitaire = None

    if depense <= 0:
        statut_calcul = "depense_indisponible"
    elif ventes_devise_incompatible:
        statut_calcul = "devise_incompatible"
    elif not attribution_observable:
        statut_calcul = "attribution_insuffisante"
    else:
        statut_calcul = "calculable"
        roas = _ratio(
            chiffre_affaires_attribue / depense
        )
        roi_publicitaire = _percent(
            (
                (
                    chiffre_affaires_attribue
                    - depense
                )
                / depense
            )
            * Decimal("100")
        )

    return {
        "campagne": campagne,
        "site_id": site_id,
        "impressions": impressions,
        "clics": clics,
        "conversions_regie": conversions,
        "depense": depense,
        "devise": devise,
        "ventes_attribuees": len(
            ventes_correspondantes
        ),
        "ventes_devise_compatible": len(
            ventes_compatibles
        ),
        "ventes_devise_incompatible": len(
            ventes_devise_incompatible
        ),
        "chiffre_affaires_attribue": (
            chiffre_affaires_attribue
        ),
        "attribution_observable": attribution_observable,
        "statut_calcul": statut_calcul,
        "roas": roas,
        "roi_publicitaire": roi_publicitaire,
        "recommandation": _recommandation(
            statut_calcul,
            roas,
        ),
        "note_roi": (
            "Le ROI affiché est un ROI publicitaire : "
            "(CA attribué - dépense publicitaire) / dépense publicitaire. "
            "Il n'intègre pas les coûts produits, salaires, logistique "
            "ou autres charges de l'entreprise."
        ),
    }
