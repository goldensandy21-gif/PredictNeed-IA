from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .attribution import appliquer_attribution_opportunite
from .models import (
    ClientProfessionnel,
    LeadCapture,
    OpportuniteCRM,
    SessionVisiteur,
    SiteClient,
)
from .views import _update_session_client_info


TEST_STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


@override_settings(STORAGES=TEST_STORAGES)
class AttributionPhase4ATests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="attribution-owner",
            email="attribution@example.com",
            password="MotDePasse-Solide-2026!",
        )
        self.client_pro = ClientProfessionnel.objects.create(
            utilisateur=self.user,
            nom_entreprise="Entreprise Attribution",
            statut_abonnement="actif",
            email_verifie_le=timezone.now(),
        )
        self.site = SiteClient.objects.create(
            client=self.client_pro,
            nom_site="Site Attribution",
            domaine="attribution.example",
            actif=True,
        )
        self.client.force_login(self.user)

    def _session_attribuee(self, session_id="campaign-session"):
        session = SessionVisiteur.objects.create(
            site=self.site,
            session_id=session_id,
        )
        _update_session_client_info(
            session,
            {
                "source_visite": "meta",
                "utm_source": "meta",
                "utm_medium": "paid_social",
                "utm_campaign": "summer-sale",
                "utm_content": "video-a",
                "utm_term": "chaussures",
                "utm_id": "cmp-123",
                "click_id_source": "meta_ads",
                "click_id": "fbclid-123",
                "landing_page": "/offre",
                "referer": "https://facebook.com/",
            },
        )
        session.save()
        return session

    def test_first_touch_is_not_overwritten_by_later_pages(self):
        session = self._session_attribuee()

        _update_session_client_info(
            session,
            {
                "source_visite": "direct",
                "utm_source": "",
                "utm_medium": "",
                "utm_campaign": "",
                "landing_page": "/page-2",
                "referer": "https://attribution.example/offre",
            },
        )
        session.save()
        session.refresh_from_db()

        self.assertEqual(session.source_visite, "meta")
        self.assertEqual(session.utm_campaign, "summer-sale")
        self.assertEqual(session.utm_content, "video-a")
        self.assertEqual(session.utm_term, "chaussures")
        self.assertEqual(session.utm_id, "cmp-123")
        self.assertEqual(session.click_id_source, "meta_ads")
        self.assertEqual(session.click_id, "fbclid-123")
        self.assertEqual(session.landing_page, "/offre")
        self.assertEqual(session.referer, "https://facebook.com/")

    def test_opportunity_keeps_campaign_snapshot(self):
        session = self._session_attribuee()
        lead = LeadCapture.objects.create(
            site=self.site,
            session=session,
            email="lead@example.com",
            consentement=True,
            statut_suivi="contacte",
        )
        opportunity = OpportuniteCRM.objects.create(
            site=self.site,
            lead=lead,
            titre="Opportunité test",
        )

        appliquer_attribution_opportunite(opportunity)
        opportunity.refresh_from_db()

        self.assertEqual(opportunity.source_attribution, "meta")
        self.assertEqual(opportunity.utm_source_attribution, "meta")
        self.assertEqual(
            opportunity.utm_campaign_attribution,
            "summer-sale",
        )
        self.assertEqual(
            opportunity.details_attribution["click_id"],
            "fbclid-123",
        )
        self.assertEqual(
            opportunity.details_attribution["landing_page"],
            "/offre",
        )

    def test_create_opportunity_from_lead_applies_snapshot(self):
        session = self._session_attribuee("from-lead")
        lead = LeadCapture.objects.create(
            site=self.site,
            session=session,
            email="create@example.com",
            consentement=True,
            statut_suivi="nouveau",
        )

        response = self.client.post(
            reverse("creer_opportunite_depuis_lead", args=[lead.id]),
        )

        self.assertEqual(response.status_code, 302)
        opportunity = OpportuniteCRM.objects.get(lead=lead)
        lead.refresh_from_db()

        self.assertEqual(
            opportunity.utm_campaign_attribution,
            "summer-sale",
        )
        self.assertEqual(lead.statut_suivi, "contacte")

    def test_snapshot_is_not_rewritten_after_creation(self):
        session = self._session_attribuee("locked-snapshot")
        lead = LeadCapture.objects.create(
            site=self.site,
            session=session,
            email="locked@example.com",
            consentement=True,
        )
        opportunity = OpportuniteCRM.objects.create(
            site=self.site,
            lead=lead,
            titre="Snapshot verrouillé",
        )
        appliquer_attribution_opportunite(opportunity)

        session.utm_campaign = "later-campaign"
        session.save(update_fields=["utm_campaign"])
        appliquer_attribution_opportunite(opportunity)
        opportunity.refresh_from_db()

        self.assertEqual(
            opportunity.utm_campaign_attribution,
            "summer-sale",
        )
