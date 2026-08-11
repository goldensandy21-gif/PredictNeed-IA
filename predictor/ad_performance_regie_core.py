from decimal import Decimal, InvalidOperation

from django.db.models import Q, Sum

from .models import SessionVisiteur, Vente


SOURCES_PAR_PLATEFORME = {
    "meta_ads": ["facebook", "instagram", "meta", "fb", "ig"],
    "tiktok_ads": ["tiktok"],
    "linkedin_ads": ["linkedin"],
}


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


def _dans_periode(queryset, champ, debut, fin):
    if debut:
        queryset = queryset.filter(**{f"{champ}__gte": debut})
    if fin:
        queryset = queryset.filter(**{f"{champ}__lte": fin})
    return queryset


def _filtre_source(plateforme):
    if plateforme == "meta_ads":
        return (
            Q(utm_source__icontains="facebook")
            | Q(utm_source__icontains="instagram")
            | Q(utm_source__icontains="meta")
            | Q(utm_source__iexact="fb")
            | Q(utm_source__iexact="ig")
        )

    if plateforme == "tiktok_ads":
        return Q(utm_source__icontains="tiktok")

    if plateforme == "linkedin_ads":
        return Q(utm_source__icontains="linkedin")

    return Q(pk__in=[])


def _source_appartient(value, plateforme):
    source = _normaliser(value)

    if not source:
        return False

    if plateforme == "meta_ads":
        return (
            "facebook" in source
            or "instagram" in source
            or "meta" in source
            or source in {"fb", "ig"}
        )

    if plateforme == "tiktok_ads":
        return "tiktok" in source

    if plateforme == "linkedin_ads":
        return "linkedin" in source

    return False


def _vente_correspond(vente, campagne, plateforme):
    vente_campaign = _normaliser(
        vente.utm_campaign_attribution
    )
    vente_source = _normaliser(
        vente.utm_source_attribution
    )
    vente_medium = _normaliser(
        vente.utm_medium_attribution
    )

    campagne_campaign = _normaliser(
        campagne.utm_campaign
    )
    campagne_source = _normaliser(
        campagne.utm_source
    )
    campagne_medium = _normaliser(
        campagne.utm_medium
    )

    if campagne_campaign:
        if vente_campaign != campagne_campaign:
            return False

        if campagne_source:
            if vente_source != campagne_source:
                return False
        elif not _source_appartient(
            vente_source,
            plateforme,
        ):
            return False

        if (
            campagne_medium
            and vente_medium != campagne_medium
        ):
            return False

        return True

    identifiant = _normaliser(
        campagne.identifiant_externe
    )

    if not identifiant:
        return False

    # Pour une campagne API native, une simple égalité
    # d'identifiant ne suffit jamais : la source doit
    # appartenir à la même régie.
    if not _source_appartient(
        vente_source,
        plateforme,
    ):
        return False

    if vente_campaign == identifiant:
        return True

    details = dict(
        vente.details_attribution or {}
    )

    return (
        _normaliser(details.get("utm_id"))
        == identifiant
    )


def _attribution_observable(
    campagne,
    plateforme,
    *,
    date_debut=None,
    date_fin=None,
    ventes_correspondantes=None,
):
    if ventes_correspondantes:
        return True

    site_id = (
        campagne.site_id
        or campagne.compte.site_id
    )

    if site_id is None:
        return False

    sessions = SessionVisiteur.objects.filter(
        site_id=site_id,
    )

    sessions = _dans_periode(
        sessions,
        "date_creation__date",
        date_debut,
        date_fin,
    )

    sessions = sessions.filter(
        _filtre_source(plateforme)
    )

    campagne_utm = str(
        campagne.utm_campaign or ""
    ).strip()

    if campagne_utm:
        return sessions.filter(
            utm_campaign=campagne_utm,
        ).exists()

    identifiant = str(
        campagne.identifiant_externe or ""
    ).strip()

    if not identifiant:
        return False

    return (
        sessions.filter(
            utm_id=identifiant
        ).exists()
        or sessions.filter(
            utm_campaign=identifiant
        ).exists()
    )


def calculer_performance_regie(
    campagne,
    *,
    plateforme_attendue,
    label_regie,
    date_debut=None,
    date_fin=None,
):
    # Double barrière : campagne ET compte.
    if campagne.plateforme != plateforme_attendue:
        raise ValueError(
            f"Campagne étrangère à {label_regie}."
        )

    if campagne.compte.plateforme != plateforme_attendue:
        raise ValueError(
            f"Compte étranger à {label_regie}."
        )

    site_id = (
        campagne.site_id
        or campagne.compte.site_id
    )

    mesures = campagne.mesures_journalieres.filter(
        plateforme=plateforme_attendue,
        compte=campagne.compte,
        site_id=site_id,
    )

    mesures = _dans_periode(
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

    impressions = int(
        totaux["impressions"] or 0
    )
    clics = int(
        totaux["clics"] or 0
    )
    conversions = _decimal(
        totaux["conversions"]
    ).quantize(Decimal("0.0001"))

    depense = _money(
        totaux["depense"]
    )

    devises = {
        str(devise or "").strip().upper()
        for devise in mesures.values_list(
            "devise",
            flat=True,
        )
        if str(devise or "").strip()
    }

    if len(devises) > 1:
        raise ValueError(
            f"Plusieurs devises détectées pour {label_regie}."
        )

    devise = (
        next(iter(devises))
        if devises
        else str(
            campagne.devise or ""
        ).strip().upper()
    )

    ctr = None
    if impressions > 0:
        ctr = _percent(
            Decimal(clics)
            / Decimal(impressions)
            * Decimal("100")
        )

    cpc_moyen = None
    if clics > 0:
        cpc_moyen = _money(
            depense / Decimal(clics)
        )

    cout_conversion = None
    if conversions > 0:
        cout_conversion = _money(
            depense / conversions
        )

    ventes = Vente.objects.filter(
        site_id=site_id,
        statut="confirmee",
    )

    ventes = _dans_periode(
        ventes,
        "date_vente",
        date_debut,
        date_fin,
    )

    ventes_correspondantes = [
        vente
        for vente in ventes
        if _vente_correspond(
            vente,
            campagne,
            plateforme_attendue,
        )
    ]

    ventes_compatibles = [
        vente
        for vente in ventes_correspondantes
        if str(
            vente.devise or ""
        ).strip().upper() == devise
    ]

    chiffre_affaires = _money(
        sum(
            (
                vente.montant
                for vente in ventes_compatibles
            ),
            Decimal("0"),
        )
    )

    attribution_observable = (
        _attribution_observable(
            campagne,
            plateforme_attendue,
            date_debut=date_debut,
            date_fin=date_fin,
            ventes_correspondantes=(
                ventes_correspondantes
            ),
        )
    )

    roas = None
    roi_publicitaire = None

    if depense > 0 and attribution_observable:
        roas = _ratio(
            chiffre_affaires / depense
        )

        roi_publicitaire = _percent(
            (
                chiffre_affaires
                - depense
            )
            / depense
            * Decimal("100")
        )

    return {
        "campagne": campagne,
        "plateforme": plateforme_attendue,
        "label_regie": label_regie,
        "impressions": impressions,
        "clics": clics,
        "conversions_regie": conversions,
        "depense": depense,
        "devise": devise,
        "ctr": ctr,
        "cpc_moyen": cpc_moyen,
        "cout_par_conversion_regie": (
            cout_conversion
        ),
        "ventes_attribuees": len(
            ventes_correspondantes
        ),
        "chiffre_affaires_attribue": (
            chiffre_affaires
        ),
        "attribution_observable": (
            attribution_observable
        ),
        "roas": roas,
        "roi_publicitaire": roi_publicitaire,
        "statut_calcul": (
            "calculable"
            if depense > 0
            and attribution_observable
            else "a_verifier"
        ),
    }
