import json
import uuid

from django.test import TestCase
from django.urls import reverse

from .models import EvenementUtilisateur, LeadCapture, SessionVisiteur


class TrackerApiKeyValidationTests(TestCase):
    def test_install_rejette_cle_non_uuid(self):
        response = self.client.get(
            reverse("tracker_installation_ping"),
            {"api_key": "invalid"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])

    def test_track_rejette_cle_non_uuid_sans_creer_donnee(self):
        response = self.client.post(
            reverse("track_event"),
            data=json.dumps({
                "api_key": "invalid",
                "session_id": "session-track-test",
                "type_evenement": "page_vue",
                "page": "/",
                "consentement_tracking": True,
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertEqual(SessionVisiteur.objects.count(), 0)
        self.assertEqual(EvenementUtilisateur.objects.count(), 0)

    def test_lead_rejette_cle_non_uuid_sans_creer_donnee(self):
        response = self.client.post(
            reverse("capture_lead"),
            data=json.dumps({
                "api_key": "invalid",
                "session_id": "session-lead-test",
                "email": "client@example.com",
                "consentement": True,
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertEqual(SessionVisiteur.objects.count(), 0)
        self.assertEqual(LeadCapture.objects.count(), 0)

    def test_install_uuid_inconnu_repond_403(self):
        response = self.client.get(
            reverse("tracker_installation_ping"),
            {"api_key": str(uuid.uuid4())},
        )
        self.assertEqual(response.status_code, 403)

    def test_track_uuid_inconnu_repond_403(self):
        response = self.client.post(
            reverse("track_event"),
            data=json.dumps({
                "api_key": str(uuid.uuid4()),
                "session_id": "session-track-test",
                "type_evenement": "page_vue",
                "page": "/",
                "consentement_tracking": True,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_lead_uuid_inconnu_repond_403(self):
        response = self.client.post(
            reverse("capture_lead"),
            data=json.dumps({
                "api_key": str(uuid.uuid4()),
                "session_id": "session-lead-test",
                "email": "client@example.com",
                "consentement": True,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
