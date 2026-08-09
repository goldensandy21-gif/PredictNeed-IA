from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date

from .models import ClientProfessionnel, SiteClient


def get_sites_utilisateur(request):
    """
    Un utilisateur possédant un espace client ne voit que ses propres sites,
    même si son compte possède aussi les droits superutilisateur.

    Un administrateur sans espace client conserve la vue globale.
    """
    client = getattr(request.user, "client_professionnel", None)

    if client is not None:
        return client.sites.all()

    if request.user.is_superuser:
        return SiteClient.objects.all()

    return SiteClient.objects.none()


def get_client_professionnel_utilisateur(request):
    try:
        return request.user.client_professionnel
    except ClientProfessionnel.DoesNotExist:
        return None


def get_module_scope(request, module_field=None, ecommerce=False):
    sites = get_sites_utilisateur(request)
    selected_site_id = (
        request.GET.get("site")
        or request.POST.get("site")
        or ""
    ).strip()

    selected_site = None
    if selected_site_id and selected_site_id != "all":
        selected_site = sites.filter(id=selected_site_id).first()
    if selected_site is None:
        selected_site = sites.order_by("date_creation").first()

    module_disponible = False
    if selected_site is not None:
        if ecommerce:
            module_disponible = bool(
                selected_site.module_ecommerce_actif
                or selected_site.type_site == "ecommerce"
            )
        elif module_field:
            module_disponible = bool(
                getattr(selected_site, module_field, False)
            )
        else:
            module_disponible = True

    if ecommerce:
        sites_actifs = sites.filter(
            Q(module_ecommerce_actif=True) | Q(type_site="ecommerce")
        )
    elif module_field:
        sites_actifs = sites.filter(**{module_field: True})
    else:
        sites_actifs = sites

    if selected_site is not None:
        selected_site_id = str(selected_site.pk)
        sites_filtres = (
            sites.filter(pk=selected_site.pk)
            if module_disponible
            else SiteClient.objects.none()
        )
    else:
        selected_site_id = ""
        sites_filtres = SiteClient.objects.none()

    return {
        "sites": sites,
        "sites_actifs": sites_actifs,
        "sites_filtres": sites_filtres,
        "selected_site": selected_site,
        "selected_site_id": selected_site_id,
        "site_selectionne_inactif": (
            selected_site is not None and not module_disponible
        ),
    }


def render_module_non_actif(request, nom_module):
    return render(request, "predictor/module_non_actif.html", {
        "nom_module": nom_module
    })


def appliquer_filtre_dates(queryset, champ_date, request):
    date_debut = request.GET.get("date_debut", "")
    date_fin = request.GET.get("date_fin", "")

    debut = parse_date(date_debut) if date_debut else None
    fin = parse_date(date_fin) if date_fin else None

    if debut:
        queryset = queryset.filter(**{f"{champ_date}__date__gte": debut})

    if fin:
        queryset = queryset.filter(**{f"{champ_date}__date__lte": fin})

    return queryset, date_debut, date_fin


def appliquer_filtre_niveau_predictions(queryset, niveau):
    if niveau == "faible":
        return queryset.filter(score__lt=3)

    if niveau == "moyen":
        return queryset.filter(score__gte=3, score__lt=6)

    if niveau == "fort":
        return queryset.filter(Q(score__gte=6) | Q(intention__iexact="Forte"))

    return queryset


def appliquer_filtre_niveau_leads(queryset, niveau):
    if niveau == "faible":
        return queryset.filter(score__lt=3)

    if niveau == "moyen":
        return queryset.filter(score__gte=3, score__lt=6)

    if niveau == "fort":
        return queryset.filter(Q(score__gte=6) | Q(intention__iexact="Forte"))

    return queryset


def extraire_montant(valeur):
    if not valeur:
        return Decimal("0")

    correspondances = re.findall(r"\d+(?:[,.]\d+)?", str(valeur))

    if not correspondances:
        return Decimal("0")

    try:
        return Decimal(correspondances[-1].replace(",", "."))
    except InvalidOperation:
        return Decimal("0")


def total_montants(evenements):
    total = Decimal("0")

    for evenement in evenements:
        total += extraire_montant(evenement.valeur)

    return total


def ajouter_largeurs(items, cle_total="total"):
    items = list(items)
    maximum = max([item.get(cle_total) or 0 for item in items], default=0)

    for item in items:
        if maximum > 0:
            item["largeur"] = round(((item.get(cle_total) or 0) / maximum) * 100)
        else:
            item["largeur"] = 0

    return items


def serie_journaliere(queryset, champ_date, nombre_jours=7):
    aujourd_hui = timezone.localdate()
    serie = []

    for index in range(nombre_jours - 1, -1, -1):
        jour = aujourd_hui - timedelta(days=index)
        total = queryset.filter(**{f"{champ_date}__date": jour}).count()

        serie.append({
            "label": jour.strftime("%d/%m"),
            "total": total,
        })

    return ajouter_largeurs(serie)
