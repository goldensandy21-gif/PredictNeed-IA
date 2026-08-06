from django.db import models
from django.conf import settings
import uuid


class ClientProfessionnel(models.Model):
    STATUT_ABONNEMENT_CHOICES = [
        ("paiement_en_attente", "Paiement en attente"),
        ("actif", "Actif"),
        ("essai", "Essai"),
        ("impaye", "Impayé"),
        ("annule", "Annulé"),
        ("expire", "Essai expiré"),
    ]

    utilisateur = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="client_professionnel"
    )

    nom_entreprise = models.CharField(max_length=150)
    secteur_activite = models.CharField(max_length=150, blank=True, null=True)
    plan_abonnement = models.CharField(max_length=80, default="predictneed_pro")
    statut_abonnement = models.CharField(
        max_length=30,
        choices=STATUT_ABONNEMENT_CHOICES,
        default="essai",
    )
    stripe_customer_id = models.CharField(max_length=120, blank=True, null=True)
    stripe_subscription_id = models.CharField(max_length=120, blank=True, null=True)
    stripe_checkout_session_id = models.CharField(max_length=160, blank=True, null=True)
    date_acceptation_cgu = models.DateTimeField(blank=True, null=True)
    date_activation_abonnement = models.DateTimeField(blank=True, null=True)
    date_debut_essai = models.DateTimeField(blank=True, null=True)
    date_fin_essai = models.DateTimeField(blank=True, null=True)
    rappel_15_jours_envoye_le = models.DateTimeField(blank=True, null=True)
    rappel_7_jours_envoye_le = models.DateTimeField(blank=True, null=True)
    rappel_2_jours_envoye_le = models.DateTimeField(blank=True, null=True)
    email_expiration_envoye_le = models.DateTimeField(blank=True, null=True)
    version_cgu_acceptee = models.CharField(max_length=30, blank=True, default="")
    version_confidentialite_acceptee = models.CharField(max_length=30, blank=True, default="")
    email_verifie_le = models.DateTimeField(blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    def abonnement_est_actif(self):
        return self.acces_donnees_autorise()


    def initialiser_essai(self, maintenant=None, enregistrer=True):
        from datetime import timedelta
        from django.conf import settings
        from django.utils import timezone

        maintenant = maintenant or timezone.now()
        self.statut_abonnement = "essai"
        self.date_debut_essai = maintenant
        self.date_fin_essai = maintenant + timedelta(
            days=settings.PREDICTNEED_SUBSCRIPTION_TRIAL_DAYS
        )
        self.rappel_15_jours_envoye_le = None
        self.rappel_7_jours_envoye_le = None
        self.rappel_2_jours_envoye_le = None
        self.email_expiration_envoye_le = None

        if enregistrer:
            self.save(
                update_fields=[
                    "statut_abonnement",
                    "date_debut_essai",
                    "date_fin_essai",
                    "rappel_15_jours_envoye_le",
                    "rappel_7_jours_envoye_le",
                    "rappel_2_jours_envoye_le",
                    "email_expiration_envoye_le",
                ]
            )
            if not self.utilisateur.is_active:
                self.utilisateur.is_active = True
                self.utilisateur.save(update_fields=["is_active"])
            self.sites.update(actif=True)

        return self


    def jours_restants_essai(self, maintenant=None):
        from django.utils import timezone

        if not self.date_fin_essai:
            return 0

        maintenant = maintenant or timezone.now()
        fin = timezone.localtime(self.date_fin_essai).date()
        aujourd_hui = timezone.localtime(maintenant).date()
        return max((fin - aujourd_hui).days, 0)


    def essai_est_valide(self, maintenant=None):
        from django.utils import timezone

        maintenant = maintenant or timezone.now()
        return bool(
            self.statut_abonnement == "essai"
            and self.date_fin_essai
            and maintenant < self.date_fin_essai
        )


    def actualiser_expiration_essai(self, maintenant=None):
        from django.utils import timezone

        maintenant = maintenant or timezone.now()

        if self.statut_abonnement != "essai":
            return self.statut_abonnement

        if not self.date_debut_essai or not self.date_fin_essai:
            self.initialiser_essai(maintenant=maintenant)
            return self.statut_abonnement

        if maintenant >= self.date_fin_essai:
            self.statut_abonnement = "expire"
            self.save(update_fields=["statut_abonnement"])
            if not self.utilisateur.is_active:
                self.utilisateur.is_active = True
                self.utilisateur.save(update_fields=["is_active"])
            self.sites.update(actif=True)

        return self.statut_abonnement


    def acces_donnees_autorise(self, maintenant=None):
        if self.statut_abonnement == "actif":
            return True

        if self.statut_abonnement == "essai":
            self.actualiser_expiration_essai(maintenant=maintenant)
            return self.essai_est_valide(maintenant=maintenant)

        return False

    def __str__(self):
        return self.nom_entreprise


class SiteClient(models.Model):
    client = models.ForeignKey(
        ClientProfessionnel,
        on_delete=models.CASCADE,
        related_name="sites"
    )

    nom_site = models.CharField(max_length=150)
    domaine = models.CharField(max_length=255)
    cle_api = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    # Détection technique du script, indépendante du consentement analytique.
    script_installe_le = models.DateTimeField(
        blank=True,
        null=True,
    )
    derniere_detection_script = models.DateTimeField(
        blank=True,
        null=True,
    )

    TYPE_SITE_CHOICES = [
        ("vitrine", "Site vitrine"),
        ("formation", "Centre de formation"),
        ("service_b2b", "Service B2B"),
        ("coach", "Coach / Consultant"),
        ("ecommerce", "E-commerce"),
        ("immobilier", "Immobilier"),
        ("beaute", "Beauté / Esthétique"),
    ]

    type_site = models.CharField(
        max_length=30,
        choices=TYPE_SITE_CHOICES,
        default="vitrine"
    )

    module_ecommerce_actif = models.BooleanField(default=False)
    module_prediction_avancee_actif = models.BooleanField(default=False)
    module_segmentation_actif = models.BooleanField(default=False)
    module_visualisations_actif = models.BooleanField(default=False)
    module_historique_actif = models.BooleanField(default=False)
    module_multicanal_actif = models.BooleanField(default=False)
    module_connecteurs_actif = models.BooleanField(default=False)
    module_publicite_actif = models.BooleanField(default=False)
    module_securite_entreprise_actif = models.BooleanField(default=False)

    retargeting_actif = models.BooleanField(default=False)
    meta_pixel_id = models.CharField(max_length=80, blank=True, null=True)
    google_ads_id = models.CharField(max_length=80, blank=True, null=True)
    google_ads_conversion_label = models.CharField(max_length=120, blank=True, null=True)
    tiktok_pixel_id = models.CharField(max_length=80, blank=True, null=True)
    linkedin_partner_id = models.CharField(max_length=80, blank=True, null=True)
    linkedin_conversion_id = models.CharField(max_length=80, blank=True, null=True)
    pinterest_tag_id = models.CharField(max_length=80, blank=True, null=True)

    def __str__(self):
        return f"{self.nom_site} - {self.domaine}"


class SessionVisiteur(models.Model):
    site = models.ForeignKey(
        SiteClient,
        on_delete=models.CASCADE,
        related_name="sessions",
        blank=True,
        null=True
    )

    session_id = models.CharField(max_length=100)
    date_creation = models.DateTimeField(auto_now_add=True)
    derniere_activite = models.DateTimeField(auto_now=True)

        # Module 1 : appareil, source et navigation
    user_agent = models.TextField(blank=True, null=True)
    referer = models.TextField(blank=True, null=True)

    appareil = models.CharField(max_length=50, blank=True, null=True)
    navigateur = models.CharField(max_length=100, blank=True, null=True)
    systeme_exploitation = models.CharField(max_length=100, blank=True, null=True)

    source_visite = models.CharField(max_length=100, blank=True, null=True)

    utm_source = models.CharField(max_length=150, blank=True, null=True)
    utm_medium = models.CharField(max_length=150, blank=True, null=True)
    utm_campaign = models.CharField(max_length=150, blank=True, null=True)

    est_mobile = models.BooleanField(default=False)
    est_tablette = models.BooleanField(default=False)
    est_desktop = models.BooleanField(default=True)

    nombre_pages_vues = models.PositiveIntegerField(default=0)
    nombre_clics = models.PositiveIntegerField(default=0)
    temps_total_secondes = models.PositiveIntegerField(default=0)
    est_rebond = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["site", "session_id"],
                name="session_unique_par_site",
            ),
            models.UniqueConstraint(
                fields=["session_id"],
                condition=models.Q(site__isnull=True),
                name="session_publique_unique_sans_site",
            ),
        ]

    def __str__(self):
        return f"Session {self.session_id}"


class EvenementUtilisateur(models.Model):
    TYPE_EVENEMENTS = [
        ("page_vue", "Page vue"),
        ("clic", "Clic"),
        ("temps", "Temps passé"),
        ("formulaire", "Formulaire"),
        ("lead", "Lead capturé"),
    ]

    session = models.ForeignKey(
        SessionVisiteur,
        on_delete=models.CASCADE,
        related_name="evenements"
    )

    type_evenement = models.CharField(
        max_length=50,
        choices=TYPE_EVENEMENTS
    )

    page = models.CharField(max_length=255)
    valeur = models.CharField(max_length=255, blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.type_evenement} - {self.page}"


class PredictionBesoin(models.Model):
    session = models.ForeignKey(
        SessionVisiteur,
        on_delete=models.CASCADE,
        related_name="predictions"
    )

    profil = models.CharField(max_length=100)
    besoin_probable = models.CharField(max_length=255)
    intention = models.CharField(max_length=50)
    score = models.IntegerField(default=0)
    recommandation = models.TextField()
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.profil} - {self.intention}"

class LeadCapture(models.Model):
    STATUT_SUIVI_CHOICES = [
        ("nouveau", "Nouveau"),
        ("contacte", "Contacté"),
        ("converti", "Converti"),
        ("perdu", "Perdu"),
    ]

    site = models.ForeignKey(
        SiteClient,
        on_delete=models.CASCADE,
        related_name="leads"
    )

    session = models.ForeignKey(
        SessionVisiteur,
        on_delete=models.CASCADE,
        related_name="leads"
    )

    nom = models.CharField(max_length=150, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    telephone = models.CharField(max_length=30, blank=True, null=True)
    message = models.TextField(blank=True, null=True)

    profil = models.CharField(max_length=100, blank=True, null=True)
    intention = models.CharField(max_length=50, blank=True, null=True)
    score = models.IntegerField(default=0)

    consentement = models.BooleanField(default=False)

    statut_suivi = models.CharField(
        max_length=30,
        choices=STATUT_SUIVI_CHOICES,
        default="nouveau"
    )

    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        contact = self.email or self.telephone or "Lead sans contact"
        return f"{contact} - {self.intention}"

class OpportuniteCRM(models.Model):
    ETAPE_CHOICES = [
        ("qualification", "Qualification"),
        ("proposition", "Proposition envoyée"),
        ("negociation", "Négociation"),
        ("gagne", "Gagné"),
        ("perdu", "Perdu"),
    ]

    site = models.ForeignKey(
        SiteClient,
        on_delete=models.CASCADE,
        related_name="opportunites"
    )

    lead = models.ForeignKey(
        LeadCapture,
        on_delete=models.SET_NULL,
        related_name="opportunites",
        blank=True,
        null=True
    )

    titre = models.CharField(max_length=200)
    montant_estime = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    etape = models.CharField(
        max_length=30,
        choices=ETAPE_CHOICES,
        default="qualification"
    )
    probabilite = models.IntegerField(default=20)
    notes = models.TextField(blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_mise_a_jour = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.titre} - {self.get_etape_display()}"


class LimitationSecurite(models.Model):
    action = models.CharField(max_length=80)
    cle_hachee = models.CharField(max_length=64)
    debut_fenetre = models.DateTimeField()
    compteur = models.PositiveIntegerField(default=0)
    derniere_tentative = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["action", "cle_hachee"],
                name="limitation_unique_action_cle",
            )
        ]
        indexes = [
            models.Index(
                fields=["action", "debut_fenetre"],
                name="limite_action_fenetre_idx",
            )
        ]

    def __str__(self):
        return f"{self.action} - {self.compteur}"


class NewsletterInscription(models.Model):
    STATUT_CHOICES = [
        ("en_attente", "En attente de confirmation"),
        ("confirmee", "Confirmée"),
        ("desinscrite", "Désinscrite"),
    ]
    prenom = models.CharField(max_length=100, blank=True, default="")
    email = models.EmailField(unique=True)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default="en_attente")
    consentement = models.BooleanField(default=False)
    version_confidentialite = models.CharField(max_length=30, blank=True, default="")
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    source = models.CharField(max_length=255, blank=True, default="")
    date_consentement = models.DateTimeField(blank=True, null=True)
    date_confirmation = models.DateTimeField(blank=True, null=True)
    date_desinscription = models.DateTimeField(blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_mise_a_jour = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_creation"]

    def __str__(self):
        return f"{self.email} - {self.get_statut_display()}"


class AutomatisationEmail(models.Model):
    TYPE_DECLENCHEUR_CHOICES = [
        ("lead_confirmation", "Confirmation automatique de demande"),
    ]

    client = models.ForeignKey(
        ClientProfessionnel,
        on_delete=models.CASCADE,
        related_name="automatisations_email"
    )
    site = models.ForeignKey(
        SiteClient,
        on_delete=models.CASCADE,
        related_name="automatisations_email",
        blank=True,
        null=True
    )
    nom = models.CharField(max_length=180, default="Confirmation de demande")
    type_declencheur = models.CharField(
        max_length=60,
        choices=TYPE_DECLENCHEUR_CHOICES,
        default="lead_confirmation"
    )
    sujet = models.CharField(
        max_length=220,
        default="Votre demande a bien été enregistrée"
    )
    contenu = models.TextField(
        default=(
            "Bonjour {nom},\n\n"
            "Votre demande a bien été enregistrée par {entreprise}. "
            "Nous reviendrons vers vous rapidement.\n\n"
            "Message reçu : {message}\n\n"
            "À bientôt,\n"
            "{entreprise}"
        )
    )
    actif = models.BooleanField(default=True)
    envoyer_copie_interne = models.BooleanField(default=False)
    email_copie = models.EmailField(blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_mise_a_jour = models.DateTimeField(auto_now=True)

    def __str__(self):
        cible = self.site.nom_site if self.site else "Tous les sites"
        return f"{self.nom} - {cible}"


class EtapeAutomatisationEmail(models.Model):
    automatisation = models.ForeignKey(
        AutomatisationEmail,
        on_delete=models.CASCADE,
        related_name="etapes"
    )
    ordre = models.PositiveIntegerField(default=1)
    nom = models.CharField(max_length=180)
    delai_jours = models.PositiveIntegerField(default=0)
    sujet = models.CharField(max_length=220)
    contenu = models.TextField()
    actif = models.BooleanField(default=True)
    stopper_si_lead_traite = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_mise_a_jour = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["automatisation", "ordre"]
        unique_together = ("automatisation", "ordre")

    def __str__(self):
        return f"{self.automatisation.nom} - étape {self.ordre}"


class EmailAutomatise(models.Model):
    STATUT_CHOICES = [
        ("envoye", "Envoyé"),
        ("erreur", "Erreur"),
        ("ignore", "Ignoré"),
    ]

    automatisation = models.ForeignKey(
        AutomatisationEmail,
        on_delete=models.SET_NULL,
        related_name="emails_envoyes",
        blank=True,
        null=True
    )
    etape = models.ForeignKey(
        EtapeAutomatisationEmail,
        on_delete=models.SET_NULL,
        related_name="emails_envoyes",
        blank=True,
        null=True
    )
    site = models.ForeignKey(
        SiteClient,
        on_delete=models.CASCADE,
        related_name="emails_automatises"
    )
    lead = models.ForeignKey(
        LeadCapture,
        on_delete=models.CASCADE,
        related_name="emails_automatises",
        blank=True,
        null=True
    )
    destinataire = models.EmailField(blank=True, null=True)
    sujet = models.CharField(max_length=220)
    message = models.TextField(blank=True, null=True)
    numero_etape = models.PositiveIntegerField(blank=True, null=True)
    date_programmee = models.DateTimeField(blank=True, null=True)
    date_envoi = models.DateTimeField(blank=True, null=True)
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default="envoye"
    )
    erreur = models.TextField(blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.destinataire or 'Sans email'} - {self.get_statut_display()}"


class CompteConnecteExterne(models.Model):
    PLATEFORME_CHOICES = [
        ("google_ads", "Google Ads"),
        ("meta_ads", "Meta Ads"),
        ("linkedin_ads", "LinkedIn Ads"),
        ("tiktok_ads", "TikTok Ads"),
    ]

    STATUT_CHOICES = [
        ("configuration_requise", "Configuration requise"),
        ("connecte", "Connecté"),
        ("erreur", "Erreur"),
        ("deconnecte", "Déconnecté"),
    ]

    client = models.ForeignKey(
        ClientProfessionnel,
        on_delete=models.CASCADE,
        related_name="comptes_externes"
    )
    site = models.ForeignKey(
        SiteClient,
        on_delete=models.SET_NULL,
        related_name="comptes_externes",
        blank=True,
        null=True
    )
    plateforme = models.CharField(max_length=40, choices=PLATEFORME_CHOICES)
    nom_compte = models.CharField(max_length=180)
    identifiant_externe = models.CharField(max_length=180, blank=True, null=True)
    statut = models.CharField(
        max_length=40,
        choices=STATUT_CHOICES,
        default="configuration_requise"
    )
    scopes = models.TextField(blank=True, null=True)
    access_token_signe = models.TextField(blank=True, null=True)
    refresh_token_signe = models.TextField(blank=True, null=True)
    token_type = models.CharField(max_length=40, blank=True, null=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    configuration = models.JSONField(default=dict, blank=True)
    dernier_message = models.TextField(blank=True, null=True)
    derniere_synchro = models.DateTimeField(blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_mise_a_jour = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["plateforme", "-date_mise_a_jour"]

    def __str__(self):
        return f"{self.get_plateforme_display()} - {self.nom_compte}"


class CampagneExterne(models.Model):
    compte = models.ForeignKey(
        CompteConnecteExterne,
        on_delete=models.CASCADE,
        related_name="campagnes"
    )
    site = models.ForeignKey(
        SiteClient,
        on_delete=models.SET_NULL,
        related_name="campagnes_externes",
        blank=True,
        null=True
    )
    plateforme = models.CharField(max_length=40, choices=CompteConnecteExterne.PLATEFORME_CHOICES)
    identifiant_externe = models.CharField(max_length=180, blank=True, null=True)
    nom = models.CharField(max_length=220)
    statut = models.CharField(max_length=80, blank=True, null=True)
    utm_source = models.CharField(max_length=150, blank=True, null=True)
    utm_medium = models.CharField(max_length=150, blank=True, null=True)
    utm_campaign = models.CharField(max_length=150, blank=True, null=True)
    impressions = models.PositiveIntegerField(default=0)
    clics = models.PositiveIntegerField(default=0)
    conversions = models.PositiveIntegerField(default=0)
    depense = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    devise = models.CharField(max_length=12, default="EUR")
    donnees_brutes = models.JSONField(default=dict, blank=True)
    derniere_synchro = models.DateTimeField(blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_mise_a_jour = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-derniere_synchro", "nom"]
        constraints = [
            models.UniqueConstraint(
                fields=["compte", "identifiant_externe"],
                name="campagne_externe_unique_par_compte",
                condition=models.Q(identifiant_externe__isnull=False),
            )
        ]

    def __str__(self):
        return f"{self.nom} - {self.get_plateforme_display()}"


class JournalSynchronisationConnecteur(models.Model):
    STATUT_CHOICES = [
        ("succes", "Succès"),
        ("erreur", "Erreur"),
        ("ignore", "Ignoré"),
    ]

    compte = models.ForeignKey(
        CompteConnecteExterne,
        on_delete=models.CASCADE,
        related_name="journaux_synchro"
    )
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES)
    message = models.TextField(blank=True, null=True)
    details = models.JSONField(default=dict, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_creation"]

    def __str__(self):
        return f"{self.compte} - {self.get_statut_display()}"
