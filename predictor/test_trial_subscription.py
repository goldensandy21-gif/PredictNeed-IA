
import json
from datetime import timedelta
from unittest.mock import patch

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

    def test_7_and_2_day_reminders_are_sent_once(self):
        _, client_7, _ = self.create_trial_client(
            timedelta(days=7)
        )
        _, client_2, _ = self.create_trial_client(
            timedelta(days=2)
        )

        call_command("gerer_essais_gratuits")
        call_command("gerer_essais_gratuits")

        client_7.refresh_from_db()
        client_2.refresh_from_db()
        self.assertEqual(len(mail.outbox), 2)
        self.assertIsNotNone(
            client_7.rappel_7_jours_envoye_le
        )
        self.assertIsNotNone(
            client_2.rappel_2_jours_envoye_le
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

    def test_public_tracker_stays_available_after_trial_expiration(self):
        _, client, site = self.create_trial_client(
            timedelta(days=-1)
        )
        call_command("gerer_essais_gratuits")
        client.refresh_from_db()
        self.assertEqual(client.statut_abonnement, "expire")

        response = self.client.post(
            reverse("track_event"),
            data=json.dumps(
                {
                    "api_key": str(site.cle_api),
                    "session_id": "expired-public-session",
                    "type_evenement": "page_vue",
                    "page": "/",
                    "consentement_tracking": True,
                }
            ),
            content_type="application/json",
            HTTP_ORIGIN="https://example.com",
        )

        self.assertEqual(response.status_code, 200)

    @override_settings(
        STRIPE_SECRET_KEY="sk_test_predictneed",
        STRIPE_PRICE_ID="price_test_predictneed",
    )
    @patch("predictor.views.create_subscription_checkout_session")
    def test_checkout_creation_is_mocked_and_saves_session_id(self, checkout):
        user, client, _ = self.create_trial_client(
            timedelta(days=-1)
        )
        client.email_verifie_le = timezone.now()
        client.save(update_fields=["email_verifie_le"])
        checkout.return_value = {
            "id": "cs_test_predictneed",
            "url": "https://checkout.stripe.test/session",
        }
        self.client.force_login(user)

        response = self.client.post(reverse("activer_abonnement"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            "https://checkout.stripe.test/session",
        )
        client.refresh_from_db()
        self.assertEqual(
            client.stripe_checkout_session_id,
            "cs_test_predictneed",
        )
        self.assertEqual(checkout.call_args.kwargs["trial_days"], 0)

    @override_settings(
        STRIPE_SECRET_KEY="sk_test_predictneed",
    )
    @patch("predictor.views.retrieve_checkout_session")
    def test_checkout_success_reactivates_expired_client(self, retrieve):
        user, client, site = self.create_trial_client(
            timedelta(days=-1)
        )
        client.statut_abonnement = "expire"
        client.stripe_checkout_session_id = "cs_test_success"
        client.save(
            update_fields=[
                "statut_abonnement",
                "stripe_checkout_session_id",
            ]
        )
        retrieve.return_value = {
            "id": "cs_test_success",
            "status": "complete",
            "payment_status": "paid",
            "customer": "cus_test_success",
            "subscription": "sub_test_success",
            "metadata": {"client_id": str(client.id)},
        }

        response = self.client.get(
            reverse("paiement_succes"),
            {"session_id": "cs_test_success"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("dashboard"))
        client.refresh_from_db()
        site.refresh_from_db()
        self.assertEqual(client.statut_abonnement, "actif")
        self.assertEqual(client.stripe_customer_id, "cus_test_success")
        self.assertEqual(
            client.stripe_subscription_id,
            "sub_test_success",
        )
        self.assertTrue(site.actif)
        self.assertEqual(
            int(self.client.session["_auth_user_id"]),
            user.id,
        )

    @override_settings(STRIPE_WEBHOOK_SECRET="whsec_test")
    @patch("predictor.views.verify_stripe_signature", return_value=True)
    def test_subscription_webhook_locks_modules_but_keeps_tracker_active(
        self,
        _signature,
    ):
        user, client, site = self.create_trial_client(
            timedelta(days=20)
        )
        client.statut_abonnement = "actif"
        client.stripe_customer_id = "cus_test_webhook"
        client.stripe_subscription_id = "sub_test_webhook"
        client.save(
            update_fields=[
                "statut_abonnement",
                "stripe_customer_id",
                "stripe_subscription_id",
            ]
        )

        event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_test_webhook",
                    "customer": "cus_test_webhook",
                    "status": "past_due",
                    "metadata": {"client_id": str(client.id)},
                }
            },
        }
        response = self.client.post(
            reverse("stripe_webhook"),
            data=json.dumps(event),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1,v1=fake",
        )

        self.assertEqual(response.status_code, 200)
        client.refresh_from_db()
        site.refresh_from_db()
        self.assertEqual(client.statut_abonnement, "impaye")
        self.assertTrue(site.actif)

        self.client.force_login(user)
        locked = self.client.get(reverse("module_prediction_avancee"))
        self.assertContains(
            locked,
            "Votre paiement doit être régularisé",
        )

        tracker = self.client.post(
            reverse("track_event"),
            data=json.dumps(
                {
                    "api_key": str(site.cle_api),
                    "session_id": "past-due-public-session",
                    "type_evenement": "page_vue",
                    "page": "/",
                    "consentement_tracking": True,
                }
            ),
            content_type="application/json",
            HTTP_ORIGIN="https://example.com",
        )
        self.assertEqual(tracker.status_code, 200)

    @override_settings(STRIPE_WEBHOOK_SECRET="whsec_test")
    @patch("predictor.views.verify_stripe_signature", return_value=True)
    def test_subscription_created_webhook_can_reactivate_client(
        self,
        _signature,
    ):
        _, client, _ = self.create_trial_client(
            timedelta(days=-1)
        )
        client.statut_abonnement = "expire"
        client.save(update_fields=["statut_abonnement"])

        event = {
            "type": "customer.subscription.created",
            "data": {
                "object": {
                    "id": "sub_created",
                    "customer": "cus_created",
                    "status": "active",
                    "metadata": {"client_id": str(client.id)},
                }
            },
        }
        response = self.client.post(
            reverse("stripe_webhook"),
            data=json.dumps(event),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1,v1=fake",
        )

        self.assertEqual(response.status_code, 200)
        client.refresh_from_db()
        self.assertEqual(client.statut_abonnement, "actif")
        self.assertEqual(client.stripe_customer_id, "cus_created")
        self.assertEqual(
            client.stripe_subscription_id,
            "sub_created",
        )
