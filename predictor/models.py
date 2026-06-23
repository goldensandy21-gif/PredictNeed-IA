from django.db import models
from django.conf import settings
import uuid


class ClientProfessionnel(models.Model):
    utilisateur = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="client_professionnel"
    )

    nom_entreprise = models.CharField(max_length=150)
    secteur_activite = models.CharField(max_length=150, blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)

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