
from django.shortcuts import render
from django.utils.deprecation import MiddlewareMixin

from .billing import format_subscription_price, stripe_is_configured


class TrialAccessMiddleware(MiddlewareMixin):
    PROTECTED_URL_NAMES = {
        "dashboard",
        "nettoyer_evenements",
        "module_prediction_avancee",
        "module_segmentation",
        "module_ecommerce",
        "module_visualisations",
        "module_historique",
        "module_multicanal",
        "module_connecteurs",
        "module_publicite",
        "module_securite",
        "demarrer_oauth_connecteur",
        "connecteur_oauth_callback",
        "synchroniser_compte_connecteur",
        "deconnecter_compte_connecteur",
        "mettre_a_jour_retargeting_site",
        "changer_statut_lead",
        "creer_opportunite_depuis_lead",
        "modifier_opportunite",
        "modifier_automatisation_email",
        "ajouter_site",
    }

    def process_view(
        self,
        request,
        view_func,
        view_args,
        view_kwargs,
    ):
        user = getattr(request, "user", None)

        if (
            user is None
            or not user.is_authenticated
            or user.is_superuser
        ):
            return None

        client = getattr(user, "client_professionnel", None)
        if client is None:
            return None

        client.actualiser_expiration_essai()

        if client.acces_donnees_autorise():
            return None

        match = getattr(request, "resolver_match", None)
        url_name = match.url_name if match is not None else None

        if url_name not in self.PROTECTED_URL_NAMES:
            return None

        sites = client.sites.all()
        selected_site_id = (
            request.GET.get("site")
            or request.POST.get("site")
            or ""
        ).strip()

        selected_site = None
        if selected_site_id:
            selected_site = sites.filter(id=selected_site_id).first()
        if selected_site is None:
            selected_site = sites.order_by("date_creation").first()

        selected_site_id = (
            str(selected_site.pk)
            if selected_site is not None
            else ""
        )

        status_code = (
            200
            if request.method in {"GET", "HEAD"}
            else 403
        )

        return render(
            request,
            "predictor/dashboard_abonnement_bloque.html",
            {
                "client_professionnel": client,
                "nom_client": client.nom_entreprise,
                "sites_disponibles": sites,
                "selected_site": selected_site,
                "selected_site_id": selected_site_id,
                "prix_abonnement": format_subscription_price(),
                "paiement_configure": stripe_is_configured(),
            },
            status=status_code,
        )
