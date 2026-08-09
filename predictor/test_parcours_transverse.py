import json
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .accounts import build_verification_token
from .ad_metrics import enregistrer_mesure_campagne_native
from .ad_performance import calculer_performance_campagne
from .models import (
    CampagneExterne,
    ClientProfessionnel,
    CompteConnecteExterne,
    EmailAutomatise,
    LeadCapture,
    MesureCampagneExterne,
    OpportuniteCRM,
    SessionVisiteur,
    SiteClient,
    Vente,
)


TEST_STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    STORAGES=TEST_STORAGES,
    STRIPE_SECRET_KEY="sk_test_predictneed",
    PREDICTNEED_SITE_URL="https://predictneed-ia.com",
)
class ParcoursTransversePredictNeedTests(TestCase):
    def test_full_local_business_journey(self):
        response = self.client.post(
            reverse("inscription"),
            {
                "username": "journey-owner",
                "email": "journey@example.com",
                "password": "MotDePasse-Solide-2026!",
                "password_confirm": "MotDePasse-Solide-2026!",
                "nom_entreprise": "Journey Corp",
                "secteur_activite": "Conseil",
                "nom_site": "Journey Site",
                "domaine": "journey.example.com",
                "accept_conditions": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("dashboard"))
        self.assertEqual(len(mail.outbox), 1)

        client_pro = ClientProfessionnel.objects.get(
            utilisateur__username="journey-owner",
        )
        site = client_pro.sites.get()
        self.assertEqual(client_pro.statut_abonnement, "essai")
        self.assertIsNone(client_pro.stripe_checkout_session_id)
        self.assertTrue(site.module_publicite_actif)

        token = build_verification_token(client_pro)
        self.client.get(
            reverse("confirmer_email_compte", args=[token])
        )
        client_pro.refresh_from_db()
        self.assertIsNotNone(client_pro.email_verifie_le)

        first_event = {
            "api_key": str(site.cle_api),
            "session_id": "journey-session",
            "type_evenement": "page_vue",
            "page": "/offre/",
            "valeur": "Offre conseil",
            "consentement_tracking": True,
            "source_visite": "google",
            "utm_source": "google",
            "utm_medium": "cpc",
            "utm_campaign": "journey-campaign",
            "utm_id": "campaign-e2e",
            "click_id_source": "google_ads",
            "click_id": "gclid-e2e",
            "landing_page": "/offre/",
        }
        self.assertEqual(
            self.client.post(
                reverse("track_event"),
                data=json.dumps(first_event),
                content_type="application/json",
                HTTP_ORIGIN="https://journey.example.com",
            ).status_code,
            200,
        )

        overwritten_event = {
            **first_event,
            "page": "/tarifs/",
            "utm_source": "direct",
            "utm_campaign": "other-campaign",
            "utm_id": "other-id",
            "click_id": "other-click",
            "landing_page": "/tarifs/",
        }
        self.client.post(
            reverse("track_event"),
            data=json.dumps(overwritten_event),
            content_type="application/json",
            HTTP_ORIGIN="https://journey.example.com",
        )

        session = SessionVisiteur.objects.get(
            site=site,
            session_id="journey-session",
        )
        self.assertEqual(session.utm_id, "campaign-e2e")
        self.assertEqual(session.click_id, "gclid-e2e")
        self.assertEqual(session.landing_page, "/offre/")

        lead_response = self.client.post(
            reverse("capture_lead"),
            data=json.dumps(
                {
                    **first_event,
                    "nom": "Lead Journey",
                    "email": "lead@journey.example",
                    "telephone": "",
                    "message": "Je souhaite être recontacté.",
                    "consentement": True,
                }
            ),
            content_type="application/json",
            HTTP_ORIGIN="https://journey.example.com",
        )
        self.assertEqual(lead_response.status_code, 200)
        lead = LeadCapture.objects.get(email="lead@journey.example")
        self.assertTrue(
            EmailAutomatise.objects.filter(
                lead=lead,
                statut="envoye",
            ).exists()
        )

        self.client.post(
            reverse("creer_opportunite_depuis_lead", args=[lead.id]),
            {"site": str(site.id)},
        )
        opportunity = OpportuniteCRM.objects.get(lead=lead)
        self.assertEqual(
            opportunity.utm_campaign_attribution,
            "journey-campaign",
        )
        self.assertEqual(
            opportunity.details_attribution["utm_id"],
            "campaign-e2e",
        )

        self.client.post(
            reverse("modifier_opportunite", args=[opportunity.id]),
            {
                "site": str(site.id),
                "montant_estime": "300",
                "montant_realise": "300",
                "devise": "EUR",
                "date_vente": "2026-08-09",
                "reference_vente": "E2E-1",
                "probabilite": "100",
                "etape": "gagne",
                "notes": "Parcours transverse",
            },
        )
        sale = Vente.objects.get(opportunite=opportunity)
        self.assertEqual(sale.montant, Decimal("300.00"))
        self.assertEqual(sale.details_attribution["utm_id"], "campaign-e2e")

        account = CompteConnecteExterne.objects.create(
            client=client_pro,
            site=site,
            plateforme="google_ads",
            nom_compte="Google Ads Journey",
            identifiant_externe="1234567890",
            statut="connecte",
        )
        campaign = CampagneExterne.objects.create(
            compte=account,
            site=site,
            plateforme="google_ads",
            source_donnees="api_regie",
            identifiant_externe="campaign-e2e",
            nom="Campaign E2E",
            devise="EUR",
        )
        enregistrer_mesure_campagne_native(
            campaign,
            date=date(2026, 8, 9),
            impressions=1000,
            clics=80,
            conversions=Decimal("1"),
            depense=Decimal("100"),
            devise="EUR",
        )
        self.assertEqual(
            MesureCampagneExterne.objects.filter(campagne=campaign).count(),
            1,
        )
        performance = calculer_performance_campagne(campaign)
        self.assertEqual(performance["roas"], Decimal("3.00"))
        self.assertEqual(
            performance["roi_publicitaire"],
            Decimal("200.0"),
        )

        second_site = SiteClient.objects.create(
            client=client_pro,
            nom_site="Second Journey Site",
            domaine="second-journey.example.com",
            actif=True,
        )
        second_session = SessionVisiteur.objects.create(
            site=second_site,
            session_id="second-site-session",
        )
        second_lead = LeadCapture.objects.create(
            site=second_site,
            session=second_session,
            email="second-site@example.com",
            consentement=True,
        )
        self.client.post(
            reverse("creer_opportunite_depuis_lead", args=[second_lead.id]),
            {"site": str(site.id)},
        )
        self.assertFalse(
            OpportuniteCRM.objects.filter(lead=second_lead).exists()
        )

        other_user = get_user_model().objects.create_user(
            username="other-journey-owner",
            email="other-journey@example.com",
            password="MotDePasse-Solide-2026!",
        )
        other_client = ClientProfessionnel.objects.create(
            utilisateur=other_user,
            nom_entreprise="Other Journey Corp",
            statut_abonnement="actif",
        )
        other_site = SiteClient.objects.create(
            client=other_client,
            nom_site="Other Journey Site",
            domaine="other-journey.example.com",
            actif=True,
        )
        other_session = SessionVisiteur.objects.create(
            site=other_site,
            session_id="other-client-session",
        )
        other_lead = LeadCapture.objects.create(
            site=other_site,
            session=other_session,
            email="other-lead@example.com",
            consentement=True,
            statut_suivi="nouveau",
        )
        cross_client = self.client.post(
            reverse("changer_statut_lead", args=[other_lead.id, "contacte"]),
            {"site": str(site.id)},
        )
        self.assertEqual(cross_client.status_code, 404)
        other_lead.refresh_from_db()
        self.assertEqual(other_lead.statut_suivi, "nouveau")

        client_pro.statut_abonnement = "essai"
        client_pro.date_fin_essai = timezone.now() - timedelta(days=1)
        client_pro.save(
            update_fields=[
                "statut_abonnement",
                "date_fin_essai",
            ]
        )
        locked = self.client.get(reverse("dashboard"), {"site": site.id})
        self.assertContains(locked, "Votre essai gratuit est terminé")

        client_pro.refresh_from_db()
        client_pro.stripe_checkout_session_id = "cs_test_e2e"
        client_pro.save(update_fields=["stripe_checkout_session_id"])

        with patch("predictor.views.retrieve_checkout_session") as retrieve:
            retrieve.return_value = {
                "id": "cs_test_e2e",
                "status": "complete",
                "payment_status": "paid",
                "customer": "cus_test_e2e",
                "subscription": "sub_test_e2e",
                "metadata": {"client_id": str(client_pro.id)},
            }
            paid = self.client.get(
                reverse("paiement_succes"),
                {"session_id": "cs_test_e2e"},
            )

        self.assertEqual(paid.status_code, 302)
        self.assertEqual(paid["Location"], reverse("dashboard"))
        client_pro.refresh_from_db()
        self.assertEqual(client_pro.statut_abonnement, "actif")
        self.assertEqual(client_pro.stripe_customer_id, "cus_test_e2e")
