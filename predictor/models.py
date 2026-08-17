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
        default="actif",
    )
    stripe_customer_id = models.CharField(max_length=120, blank=True, null=True)
    stripe_subscription_id = models.CharField(max_length=120, blank=True, null=True)
    stripe_checkout_session_id = models.CharField(max_length=160, blank=True, null=True)
    date_acceptation_cgu = models.DateTimeField(blank=True, null=True)
    date_activation_abonnement = models.DateTimeField(blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    def abonnement_est_actif(self):
        return self.statut_abonnement in {"actif", "essai"}

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

    session_id = models.CharField(max_length=100, unique=True)
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


# ---------------------------------------------------------------------------
# Attribution ProspectPilot — ferme la boucle acquisition -> conversion.
#
# `token` est un identifiant opaque généré par ProspectPilot (paramètre `ppt`
# des liens de campagne) : on ne cherche jamais à en déduire un prospect_id,
# campaign_id ou email_id ProspectPilot. PredictNeed se contente de le
# conserver et de le renvoyer tel quel dans les événements sortants.
# ---------------------------------------------------------------------------

class ProspectPilotAttribution(models.Model):
    token = models.CharField(max_length=128, unique=True, db_index=True)
    session_key = models.CharField(max_length=64, blank=True, db_index=True)
    client_professionnel = models.ForeignKey(
        ClientProfessionnel,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="prospectpilot_attributions",
    )

    landing_url = models.CharField(max_length=2000, blank=True)
    utm_source = models.CharField(max_length=150, blank=True)
    utm_medium = models.CharField(max_length=150, blank=True)
    utm_campaign = models.CharField(max_length=150, blank=True)
    utm_content = models.CharField(max_length=150, blank=True)

    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    active = models.BooleanField(default=True)

    # Garde-fous anti-doublon en plus de la clé d'idempotence côté événement.
    product_visited_sent = models.BooleanField(default=False)
    simulator_started_sent = models.BooleanField(default=False)
    signup_completed_sent = models.BooleanField(default=False)
    checkout_started_sent = models.BooleanField(default=False)

    class Meta:
        ordering = ["-last_seen_at"]

    def __str__(self):
        return f"Attribution ProspectPilot {self.token[:16]}…"


class ProspectPilotOutboundEvent(models.Model):
    """File d'attente locale des événements à transmettre à ProspectPilot.

    Ce dépôt n'utilise pas Celery/Redis : la fiabilité vient d'ici (écriture
    immédiate en base avant tout appel réseau) plutôt que d'une file de
    tâches. Une commande de gestion (`retry_prospectpilot_events`, à lancer
    par le même mécanisme cron que `envoyer_relances_automatiques`) relance
    les événements en échec transitoire.
    """
    STATUT_CHOICES = [
        ("pending", "En attente"),
        ("sending", "Envoi en cours"),
        ("sent", "Envoyé"),
        ("failed", "Échec (nouvel essai prévu)"),
        ("dead_letter", "Abandonné"),
    ]

    event_id = models.CharField(max_length=180, unique=True, db_index=True)
    event_type = models.CharField(max_length=40, db_index=True)
    attribution = models.ForeignKey(
        ProspectPilotAttribution,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="outbound_events",
    )
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=STATUT_CHOICES, default="pending", db_index=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event_type} ({self.get_status_display()})"
