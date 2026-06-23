from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import (
    ClientProfessionnel,
    SiteClient,
    SessionVisiteur,
    EvenementUtilisateur,
    PredictionBesoin,
    LeadCapture,
)


@admin.register(ClientProfessionnel)
class ClientProfessionnelAdmin(admin.ModelAdmin):
    list_display = ("nom_entreprise", "secteur_activite", "utilisateur", "date_creation")


@admin.register(SiteClient)
class SiteClientAdmin(admin.ModelAdmin):
    list_display = ("nom_site", "domaine", "client", "cle_api", "actif")
    readonly_fields = ("cle_api", "date_creation")


@admin.register(SessionVisiteur)
class SessionVisiteurAdmin(admin.ModelAdmin):
    list_display = ("session_id", "site", "date_creation", "derniere_activite")


@admin.register(EvenementUtilisateur)
class EvenementUtilisateurAdmin(admin.ModelAdmin):
    list_display = ("type_evenement", "page", "valeur", "session", "date_creation")


@admin.register(LeadCapture)
class LeadCaptureAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "telephone",
        "site",
        "profil",
        "intention",
        "score",
        "statut_suivi",
        "date_creation",
    )

    list_editable = ("statut_suivi",)

    list_filter = (
        "statut_suivi",
        "intention",
        "consentement",
    )

    search_fields = (
        "email",
        "telephone",
        "nom",
    )

    readonly_fields = ("date_creation",)