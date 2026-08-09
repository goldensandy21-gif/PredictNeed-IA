
import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .accounts import build_verification_token
from .models import (
    ClientProfessionnel,
    EvenementUtilisateur,
    LimitationSecurite,
    SessionVisiteur,
    SiteClient,
)
from .security_middleware import PublicRateLimitMiddleware


TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    STORAGES=TEST_STORAGES,
    PREDICTNEED_SITE_URL="https://predictneed-ia.com",
    PREDICTNEED_CONTACT_EMAIL="contact@example.com",
)
class SecurityAndMultiSiteTests(TestCase):
    def create_client(self, username="client", verified=True):
        user = get_user_model().objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="MotDePasse-Solide-2026!",
        )
        client = ClientProfessionnel.objects.create(
            utilisateur=user,
            nom_entreprise="Entreprise",
            statut_abonnement="actif",
            email_verifie_le=timezone.now() if verified else None,
        )
        return user, client

    def test_signup_rejects_weak_password(self):
        response = self.client.post(
            reverse("inscription"),
            {
                "username": "faible",
                "email": "faible@example.com",
                "password": "12345678",
                "password_confirm": "12345678",
                "nom_entreprise": "Entreprise",
                "secteur_activite": "Conseil",
                "nom_site": "Site",
                "domaine": "example.com",
                "accept_conditions": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username="faible").exists())

    def test_signup_records_versions_and_sends_verification(self):
        response = self.client.post(
            reverse("inscription"),
            {
                "username": "nouveau-securise",
                "email": "nouveau-securise@example.com",
                "password": "MotDePasse-Solide-2026!",
                "password_confirm": "MotDePasse-Solide-2026!",
                "nom_entreprise": "Entreprise",
                "secteur_activite": "Conseil",
                "nom_site": "Site",
                "domaine": "https://www.example.com/une-page",
                "accept_conditions": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        client = ClientProfessionnel.objects.get(
            utilisateur__username="nouveau-securise"
        )
        self.assertEqual(client.version_cgu_acceptee, "2026-08-06")
        self.assertEqual(client.version_confidentialite_acceptee, "2026-08-06")
        self.assertIsNone(client.email_verifie_le)
        self.assertEqual(client.sites.get().domaine, "example.com")
        self.assertEqual(len(mail.outbox), 1)

        token = build_verification_token(client)
        confirmation = self.client.get(
            reverse("confirmer_email_compte", args=[token])
        )
        self.assertEqual(confirmation.status_code, 200)
        client.refresh_from_db()
        self.assertIsNotNone(client.email_verifie_le)

    def test_password_reset_sends_email_without_disclosing_account(self):
        self.create_client("reset-user")
        response = self.client.post(
            reverse("password_reset"),
            {"email": "reset-user@example.com"},
        )
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)

    def test_same_session_identifier_is_isolated_per_site(self):
        _, client = self.create_client("multi")
        site_a = SiteClient.objects.create(
            client=client,
            nom_site="A",
            domaine="a.example.com",
        )
        site_b = SiteClient.objects.create(
            client=client,
            nom_site="B",
            domaine="b.example.com",
        )
        SessionVisiteur.objects.create(site=site_a, session_id="same-id")
        SessionVisiteur.objects.create(site=site_b, session_id="same-id")
        self.assertEqual(
            SessionVisiteur.objects.filter(session_id="same-id").count(),
            2,
        )

    def test_tracker_rejects_unknown_event_and_keeps_sites_separate(self):
        _, client = self.create_client("tracker")
        site_a = SiteClient.objects.create(
            client=client,
            nom_site="A",
            domaine="a.example.com",
        )
        site_b = SiteClient.objects.create(
            client=client,
            nom_site="B",
            domaine="b.example.com",
        )
        invalid = self.client.post(
            reverse("track_event"),
            data=json.dumps(
                {
                    "api_key": str(site_a.cle_api),
                    "session_id": "same-id",
                    "type_evenement": "inconnu",
                    "page": "/",
                    "consentement_tracking": True,
                }
            ),
            content_type="application/json",
            HTTP_ORIGIN="https://a.example.com",
        )
        self.assertEqual(invalid.status_code, 400)

        for site, origin in [
            (site_a, "https://a.example.com"),
            (site_b, "https://b.example.com"),
        ]:
            response = self.client.post(
                reverse("track_event"),
                data=json.dumps(
                    {
                        "api_key": str(site.cle_api),
                        "session_id": "same-id",
                        "type_evenement": "page_vue",
                        "page": "/prix/",
                        "consentement_tracking": True,
                    }
                ),
                content_type="application/json",
                HTTP_ORIGIN=origin,
            )
            self.assertEqual(response.status_code, 200)

        self.assertEqual(
            SessionVisiteur.objects.filter(session_id="same-id").count(),
            2,
        )

    def test_tracker_rejects_foreign_origin_for_valid_site_key(self):
        _, client = self.create_client("tracker-origin")
        site = SiteClient.objects.create(
            client=client,
            nom_site="Site origine",
            domaine="site.example.com",
        )

        response = self.client.post(
            reverse("track_event"),
            data=json.dumps(
                {
                    "api_key": str(site.cle_api),
                    "session_id": "origin-session",
                    "type_evenement": "page_vue",
                    "page": "/",
                    "consentement_tracking": True,
                }
            ),
            content_type="application/json",
            HTTP_ORIGIN="https://evil.example.com",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            SessionVisiteur.objects.filter(
                site=site,
                session_id="origin-session",
            ).exists()
        )

    def test_tracker_event_has_persistent_rate_limit(self):
        _, client = self.create_client("tracker-rate")
        site = SiteClient.objects.create(
            client=client,
            nom_site="Site rate limit",
            domaine="rate.example.com",
        )

        with patch.dict(
            PublicRateLimitMiddleware.RULES,
            {"track_event": (2, 300, "api")},
        ):
            for index in range(3):
                response = self.client.post(
                    reverse("track_event"),
                    data=json.dumps(
                        {
                            "api_key": str(site.cle_api),
                            "session_id": f"rate-session-{index}",
                            "type_evenement": "page_vue",
                            "page": "/",
                            "consentement_tracking": True,
                        }
                    ),
                    content_type="application/json",
                    HTTP_ORIGIN="https://rate.example.com",
                    REMOTE_ADDR="203.0.113.99",
                )

        self.assertEqual(response.status_code, 429)
        entry = LimitationSecurite.objects.get(action="track_event")
        self.assertEqual(len(entry.cle_hachee), 64)
        self.assertNotIn(str(site.cle_api), entry.cle_hachee)

    def test_clean_events_only_affects_selected_site(self):
        user, client = self.create_client("clean")
        site_a = SiteClient.objects.create(
            client=client,
            nom_site="A",
            domaine="a.example.com",
        )
        site_b = SiteClient.objects.create(
            client=client,
            nom_site="B",
            domaine="b.example.com",
        )
        session_a = SessionVisiteur.objects.create(site=site_a, session_id="a")
        session_b = SessionVisiteur.objects.create(site=site_b, session_id="b")
        EvenementUtilisateur.objects.create(
            session=session_a,
            type_evenement="page_vue",
            page="/a/",
        )
        EvenementUtilisateur.objects.create(
            session=session_b,
            type_evenement="page_vue",
            page="/b/",
        )
        self.client.force_login(user)
        response = self.client.post(
            reverse("nettoyer_evenements"),
            {"site": str(site_a.pk)},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(EvenementUtilisateur.objects.filter(session=session_a).exists())
        self.assertTrue(EvenementUtilisateur.objects.filter(session=session_b).exists())

    def test_module_scope_checks_selected_site(self):
        user, client = self.create_client("modules")
        active = SiteClient.objects.create(
            client=client,
            nom_site="Actif",
            domaine="active.example.com",
            module_prediction_avancee_actif=True,
        )
        inactive = SiteClient.objects.create(
            client=client,
            nom_site="Inactif",
            domaine="inactive.example.com",
            module_prediction_avancee_actif=False,
        )
        self.client.force_login(user)
        response = self.client.get(
            reverse("module_prediction_avancee"),
            {"site": inactive.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "predictor/module_non_actif.html")

        response = self.client.get(
            reverse("module_prediction_avancee"),
            {"site": active.pk},
        )
        self.assertEqual(response.status_code, 200)

    def test_rate_limit_is_stored_as_hash(self):
        for index in range(6):
            response = self.client.post(
                reverse("newsletter_inscription"),
                {
                    "email": f"rate-{index}@example.com",
                    "guides_consent": "on",
                    "next": "/",
                },
                REMOTE_ADDR="203.0.113.9",
            )
        self.assertEqual(response.status_code, 429)
        entry = LimitationSecurite.objects.get(action="newsletter_inscription")
        self.assertEqual(len(entry.cle_hachee), 64)
        self.assertNotIn("203.0.113.9", entry.cle_hachee)
