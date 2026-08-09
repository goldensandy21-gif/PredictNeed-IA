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
    OpportuniteCRM,
    AutomatisationEmail,
    EtapeAutomatisationEmail,
    EmailAutomatise,
    CompteConnecteExterne,
    CampagneExterne,
    JournalSynchronisationConnecteur,
    NewsletterInscription,
    LimitationSecurite,
    ModeleMachineLearning,
    JournalMaintenance,
)


@admin.register(ClientProfessionnel)
class ClientProfessionnelAdmin(admin.ModelAdmin):
    list_display = (
        "nom_entreprise",
        "secteur_activite",
        "utilisateur",
        "statut_abonnement",
        "plan_abonnement",
        "date_activation_abonnement",
        "date_creation",
    )
    list_filter = ("statut_abonnement", "plan_abonnement")
    search_fields = (
        "nom_entreprise",
        "utilisateur__username",
        "utilisateur__email",
        "stripe_customer_id",
        "stripe_subscription_id",
    )
    readonly_fields = (
        "stripe_customer_id",
        "stripe_subscription_id",
        "stripe_checkout_session_id",
        "date_acceptation_cgu",
        "date_activation_abonnement",
        "version_cgu_acceptee",
        "version_confidentialite_acceptee",
        "email_verifie_le",
        "date_creation",
    )


@admin.register(SiteClient)
class SiteClientAdmin(admin.ModelAdmin):
    list_display = (
        "nom_site",
        "domaine",
        "client",
        "cle_api",
        "type_site",
        "module_ecommerce_actif",
        "module_prediction_avancee_actif",
        "module_segmentation_actif",
        "module_visualisations_actif",
        "module_historique_actif",
        "module_multicanal_actif",
        "module_connecteurs_actif",
        "module_publicite_actif",
        "module_securite_entreprise_actif",
        "retargeting_actif",
        "actif",
        "date_creation",
    )

    list_filter = (
        "type_site",
        "module_ecommerce_actif",
        "module_prediction_avancee_actif",
        "module_segmentation_actif",
        "module_visualisations_actif",
        "module_historique_actif",
        "module_multicanal_actif",
        "module_connecteurs_actif",
        "module_publicite_actif",
        "module_securite_entreprise_actif",
        "retargeting_actif",
        "actif",
    )

    search_fields = (
        "nom_site",
        "domaine",
        "client__nom_entreprise",
    )

    list_editable = (
        "type_site",
        "module_ecommerce_actif",
        "module_prediction_avancee_actif",
        "module_segmentation_actif",
        "module_visualisations_actif",
        "module_historique_actif",
        "module_multicanal_actif",
        "module_connecteurs_actif",
        "module_publicite_actif",
        "module_securite_entreprise_actif",
        "retargeting_actif",
        "actif",
    )

    readonly_fields = ("cle_api", "date_creation")


@admin.register(SessionVisiteur)
class SessionVisiteurAdmin(admin.ModelAdmin):
    list_display = (
        "session_id_court",
        "site",
        "appareil",
        "navigateur",
        "systeme_exploitation",
        "source_visite",
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_content",
        "click_id_source",
        "landing_page",
        "nombre_pages_vues",
        "nombre_clics",
        "temps_total_secondes",
        "est_rebond",
        "date_creation",
        "derniere_activite",
    )

    list_filter = (
        "appareil",
        "navigateur",
        "systeme_exploitation",
        "est_mobile",
        "est_tablette",
        "est_desktop",
        "est_rebond",
        "utm_source",
    )

    search_fields = (
        "session_id",
        "site__nom_site",
        "site__domaine",
        "source_visite",
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_content",
        "utm_term",
        "utm_id",
        "click_id_source",
        "click_id",
        "landing_page",
        "navigateur",
        "systeme_exploitation",
    )

    readonly_fields = (
        "session_id",
        "site",
        "user_agent",
        "referer",
        "appareil",
        "navigateur",
        "systeme_exploitation",
        "source_visite",
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_content",
        "utm_term",
        "utm_id",
        "click_id_source",
        "click_id",
        "landing_page",
        "est_mobile",
        "est_tablette",
        "est_desktop",
        "nombre_pages_vues",
        "nombre_clics",
        "temps_total_secondes",
        "est_rebond",
        "date_creation",
        "derniere_activite",
    )

    def session_id_court(self, obj):
        if obj.session_id:
            return obj.session_id[:12] + "..."
        return "-"

    session_id_court.short_description = "Session"


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

@admin.register(OpportuniteCRM)
class OpportuniteCRMAdmin(admin.ModelAdmin):
    list_display = (
        "titre",
        "site",
        "lead",
        "montant_estime",
        "etape",
        "probabilite",
        "utm_campaign_attribution",
        "date_creation",
    )
    list_filter = ("etape", "site", "utm_source_attribution")
    search_fields = (
        "titre",
        "lead__email",
        "lead__telephone",
        "utm_campaign_attribution",
    )
    readonly_fields = (
        "source_attribution",
        "utm_source_attribution",
        "utm_medium_attribution",
        "utm_campaign_attribution",
        "details_attribution",
        "date_creation",
        "date_mise_a_jour",
    )


class EtapeAutomatisationEmailInline(admin.TabularInline):
    model = EtapeAutomatisationEmail
    extra = 0
    fields = (
        "ordre",
        "nom",
        "delai_jours",
        "sujet",
        "actif",
        "stopper_si_lead_traite",
    )


@admin.register(AutomatisationEmail)
class AutomatisationEmailAdmin(admin.ModelAdmin):
    list_display = (
        "nom",
        "client",
        "site",
        "type_declencheur",
        "actif",
        "envoyer_copie_interne",
        "date_mise_a_jour",
    )
    list_filter = ("actif", "type_declencheur", "envoyer_copie_interne", "site")
    inlines = [EtapeAutomatisationEmailInline]
    search_fields = (
        "nom",
        "sujet",
        "contenu",
        "client__nom_entreprise",
        "site__nom_site",
    )
    readonly_fields = ("date_creation", "date_mise_a_jour")


@admin.register(EmailAutomatise)
class EmailAutomatiseAdmin(admin.ModelAdmin):
    list_display = (
        "destinataire",
        "sujet",
        "site",
        "lead",
        "numero_etape",
        "statut",
        "date_creation",
    )
    list_filter = ("statut", "site", "date_creation")
    search_fields = (
        "destinataire",
        "sujet",
        "message",
        "erreur",
        "lead__email",
        "lead__telephone",
    )
    readonly_fields = (
        "automatisation",
        "etape",
        "site",
        "lead",
        "destinataire",
        "sujet",
        "message",
        "numero_etape",
        "date_programmee",
        "date_envoi",
        "statut",
        "erreur",
        "date_creation",
    )


@admin.register(EtapeAutomatisationEmail)
class EtapeAutomatisationEmailAdmin(admin.ModelAdmin):
    list_display = (
        "automatisation",
        "ordre",
        "nom",
        "delai_jours",
        "actif",
        "stopper_si_lead_traite",
        "date_mise_a_jour",
    )
    list_filter = ("actif", "stopper_si_lead_traite", "delai_jours")
    search_fields = ("nom", "sujet", "contenu", "automatisation__nom")
    readonly_fields = ("date_creation", "date_mise_a_jour")


@admin.register(CompteConnecteExterne)
class CompteConnecteExterneAdmin(admin.ModelAdmin):
    list_display = (
        "nom_compte",
        "plateforme",
        "client",
        "site",
        "statut",
        "identifiant_externe",
        "derniere_synchro",
        "date_mise_a_jour",
    )
    list_filter = ("plateforme", "statut", "site")
    search_fields = (
        "nom_compte",
        "identifiant_externe",
        "client__nom_entreprise",
        "site__nom_site",
    )
    readonly_fields = (
        "access_token_signe",
        "refresh_token_signe",
        "configuration",
        "date_creation",
        "date_mise_a_jour",
    )


@admin.register(CampagneExterne)
class CampagneExterneAdmin(admin.ModelAdmin):
    list_display = (
        "nom",
        "plateforme",
        "compte",
        "site",
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "clics",
        "conversions",
        "depense",
        "derniere_synchro",
    )
    list_filter = ("plateforme", "site", "devise")
    search_fields = (
        "nom",
        "identifiant_externe",
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "compte__nom_compte",
    )
    readonly_fields = ("donnees_brutes", "date_creation", "date_mise_a_jour")


@admin.register(JournalSynchronisationConnecteur)
class JournalSynchronisationConnecteurAdmin(admin.ModelAdmin):
    list_display = ("compte", "statut", "message", "date_creation")
    list_filter = ("statut", "compte__plateforme")
    search_fields = ("compte__nom_compte", "message")
    readonly_fields = ("compte", "statut", "message", "details", "date_creation")


@admin.register(PredictionBesoin)
class PredictionBesoinAdmin(admin.ModelAdmin):
    list_display = (
        "session",
        "profil",
        "intention",
        "score",
        "moteur",
        "probabilite_conversion",
        "version_modele",
        "date_creation",
    )
    list_filter = ("moteur", "intention", "date_creation")
    search_fields = (
        "session__session_id",
        "session__site__nom_site",
        "profil",
        "besoin_probable",
        "version_modele",
    )
    readonly_fields = (
        "session",
        "profil",
        "besoin_probable",
        "intention",
        "score",
        "recommandation",
        "moteur",
        "probabilite_conversion",
        "version_modele",
        "date_creation",
    )


@admin.register(ModeleMachineLearning)
class ModeleMachineLearningAdmin(admin.ModelAdmin):
    list_display = (
        "site",
        "version",
        "actif",
        "nombre_echantillons",
        "nombre_positifs",
        "nombre_negatifs",
        "date_entrainement",
    )
    list_filter = ("actif", "site", "date_entrainement")
    search_fields = ("site__nom_site", "site__domaine", "version")
    readonly_fields = (
        "site",
        "version",
        "actif",
        "noms_caracteristiques",
        "coefficients",
        "moyennes_caracteristiques",
        "echelles_caracteristiques",
        "intercept",
        "seuil_intention_forte",
        "metriques",
        "nombre_echantillons",
        "nombre_positifs",
        "nombre_negatifs",
        "date_entrainement",
    )


@admin.register(JournalMaintenance)
class JournalMaintenanceAdmin(admin.ModelAdmin):
    list_display = (
        "type_operation",
        "statut",
        "date_debut",
        "date_fin",
    )
    list_filter = ("type_operation", "statut", "date_debut")
    search_fields = ("message_erreur",)
    readonly_fields = (
        "type_operation",
        "statut",
        "details",
        "message_erreur",
        "date_debut",
        "date_fin",
    )


@admin.register(NewsletterInscription)
class NewsletterInscriptionAdmin(admin.ModelAdmin):
    list_display = ("email", "prenom", "statut", "consentement", "date_confirmation", "date_desinscription", "date_creation")
    list_filter = ("statut", "consentement", "date_creation")
    search_fields = ("email", "prenom")
    readonly_fields = ("token", "date_consentement", "date_confirmation", "date_desinscription", "date_creation", "date_mise_a_jour")


@admin.register(LimitationSecurite)
class LimitationSecuriteAdmin(admin.ModelAdmin):
    list_display = (
        "action",
        "cle_hachee_courte",
        "compteur",
        "debut_fenetre",
        "derniere_tentative",
    )
    list_filter = ("action", "debut_fenetre")
    search_fields = ("action", "cle_hachee")
    readonly_fields = (
        "action",
        "cle_hachee",
        "debut_fenetre",
        "compteur",
        "derniere_tentative",
    )

    @admin.display(description="Clé hachée")
    def cle_hachee_courte(self, obj):
        return f"{obj.cle_hachee[:12]}…"


# Accès Django Admin réservé aux superutilisateurs
def _predictneed_admin_superuser_only(request):
    return bool(
        request.user.is_authenticated
        and request.user.is_active
        and request.user.is_superuser
    )


admin.site.has_permission = _predictneed_admin_superuser_only
