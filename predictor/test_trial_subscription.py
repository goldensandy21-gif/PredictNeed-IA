
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import ClientProfessionnel, SiteClient


TEST_STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
        ),
    },
}


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    STORAGES=TEST_STORAGES,
    STRIPE_SECRET_KEY="",
    PREDICTNEED_SITE_URL="https://predictneed-ia.com",
)
class FreeTrialTests(TestCase):
    def create_trial_client(self, end_delta):
        User = get_user_model()
        index = User.objects.count() + 1
        user = User.objects.create_user(
            username=f"user-{index}",
            email=f"user-{index}@example.com",
            password="mot-de-passe-test",
            is_active=True,
        )
        now = timezone.now()
        client = ClientProfessionnel.objects.create(
            utilisateur=user,
            nom_entreprise="Entreprise test",
            statut_abonnement="essai",
            date_debut_essai=now - timedelta(days=1),
            date_fin_essai=now + end_delta,
        )
        site = SiteClient.objects.create(
            client=client,
            nom_site="Site test",
            domaine="example.com",
            actif=True,
            module_prediction_avancee_actif=True,
        )
        return user, client, site

    def test_signup_creates_active_trial_without_stripe(self):
        response = self.client.post(
            reverse("inscription"),
            {
                "username": "nouveau-client",
                "email": "nouveau@example.com",
                "password": "mot-de-passe-test",
                "nom_entreprise": "Nouvelle entreprise",
                "secteur_activite": "Conseil",
                "nom_site": "Nouveau site",
                "domaine": "nouveau.example",
                "accept_conditions": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard"))

        client = ClientProfessionnel.objects.get(
            utilisateur__username="nouveau-client"
        )
        self.assertEqual(client.statut_abonnement, "essai")
        self.assertTrue(client.utilisateur.is_active)
        self.assertIsNotNone(client.date_debut_essai)
        self.assertIsNotNone(client.date_fin_essai)
        self.assertTrue(client.sites.filter(actif=True).exists())
        self.assertFalse(client.stripe_checkout_session_id)

    def test_expired_dashboard_is_locked(self):
        user, client, _ = self.create_trial_client(
            timedelta(days=-1)
        )
        self.client.force_login(user)

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Votre essai gratuit est terminé",
        )
        client.refresh_from_db()
        user.refresh_from_db()
        self.assertEqual(client.statut_abonnement, "expire")
        self.assertTrue(user.is_active)

    def test_expired_module_is_locked(self):
        user, _, _ = self.create_trial_client(
            timedelta(days=-1)
        )
        self.client.force_login(user)

        response = self.client.get(
            reverse("module_prediction_avancee")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Votre essai gratuit est terminé",
        )

    def test_reminder_is_sent_once(self):
        _, client, _ = self.create_trial_client(
            timedelta(days=15)
        )

        call_command("gerer_essais_gratuits")
        call_command("gerer_essais_gratuits")

        client.refresh_from_db()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIsNotNone(
            client.rappel_15_jours_envoye_le
        )

    def test_expiration_keeps_user_and_site_active(self):
        user, client, site = self.create_trial_client(
            timedelta(days=-1)
        )

        call_command("gerer_essais_gratuits")

        client.refresh_from_db()
        user.refresh_from_db()
        site.refresh_from_db()

        self.assertEqual(client.statut_abonnement, "expire")
        self.assertTrue(user.is_active)
        self.assertTrue(site.actif)
