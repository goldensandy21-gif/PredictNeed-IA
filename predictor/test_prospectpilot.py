"""Tests de l'intégration ProspectPilot <-> PredictNeed IA (attribution ppt,
émission d'événements, activation d'abonnement depuis le webhook Stripe)."""
import json
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from predictor.billing import _stripe_request  # noqa: F401  (import sanity)
from predictor.models import (
    ClientProfessionnel,
    ProspectPilotAttribution,
    ProspectPilotOutboundEvent,
)
from predictor.services.prospectpilot_attribution import (
    capture_prospectpilot_attribution,
    get_attribution_for_client,
    get_current_attribution,
)
from predictor.services.prospectpilot_events import (
    normalize_to_monthly,
    retry_due_events,
    send_prospectpilot_event,
)


class FakeHTTPResponse:
    def __init__(self, status=200, body=b"{}"):
        self.status = status
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class AttributionCaptureTests(TestCase):
    def test_valid_ppt_creates_attribution(self):
        response = self.client.get("/?ppt=abcDEF1234567890xyz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ProspectPilotAttribution.objects.count(), 1)
        attribution = ProspectPilotAttribution.objects.get()
        self.assertEqual(attribution.token, "abcDEF1234567890xyz")

    def test_no_ppt_does_not_create_attribution(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ProspectPilotAttribution.objects.count(), 0)

    def test_empty_ppt_ignored(self):
        response = self.client.get("/?ppt=")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ProspectPilotAttribution.objects.count(), 0)

    def test_too_long_or_invalid_ppt_ignored(self):
        response = self.client.get("/?ppt=" + ("a" * 300))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ProspectPilotAttribution.objects.count(), 0)

    def test_invalid_characters_ignored(self):
        response = self.client.get("/?ppt=" + "abc def<script>")
        self.assertEqual(ProspectPilotAttribution.objects.count(), 0)

    def test_attribution_kept_in_session_across_requests(self):
        self.client.get("/?ppt=firsttouchtoken123")
        response = self.client.get("/fonctionnalites/")
        self.assertEqual(response.status_code, 200)
        # La session conserve l'attribution même sans nouveau paramètre ppt.
        session = self.client.session
        self.assertIn("prospectpilot_attribution_id", session)

    def test_first_touch_not_overwritten_by_second_token(self):
        self.client.get("/?ppt=firsttouchtoken123")
        first_id = self.client.session["prospectpilot_attribution_id"]
        self.client.get("/?ppt=secondtouchtoken456")
        second_id = self.client.session["prospectpilot_attribution_id"]
        self.assertEqual(first_id, second_id)
        # Le second token est tout de même journalisé pour l'historique.
        self.assertEqual(ProspectPilotAttribution.objects.count(), 2)

    def test_capture_never_raises_on_broken_session(self):
        factory_request = MagicMock()
        factory_request.GET = {"ppt": "validtoken1234567"}
        factory_request.session.session_key = None
        factory_request.session.create.side_effect = Exception("boom")
        result = capture_prospectpilot_attribution(factory_request)
        self.assertIsNone(result)


class MRRNormalizationTests(TestCase):
    def test_monthly_price_unchanged(self):
        self.assertEqual(normalize_to_monthly(99, "month"), 99)

    def test_annual_price_normalized(self):
        self.assertEqual(normalize_to_monthly(1188, "year"), 99)

    def test_none_amount_returns_none(self):
        self.assertIsNone(normalize_to_monthly(None, "month"))


@override_settings(PROSPECTPILOT_API_URL="https://prospectpilot.example", PROSPECTPILOT_SHARED_SECRET="s3cr3t")
class SendEventTests(TestCase):
    def _attribution(self):
        return ProspectPilotAttribution.objects.create(token="tok1234567890abcd")

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_successful_send_marks_event_sent(self, mock_urlopen):
        mock_urlopen.return_value = FakeHTTPResponse(200)
        attribution = self._attribution()
        event = send_prospectpilot_event("simulator_started", attribution=attribution, idempotency_key="k1")
        self.assertEqual(event.status, "sent")
        self.assertEqual(event.attempt_count, 1)

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_duplicate_idempotency_key_not_resent(self, mock_urlopen):
        mock_urlopen.return_value = FakeHTTPResponse(200)
        attribution = self._attribution()
        send_prospectpilot_event("simulator_started", attribution=attribution, idempotency_key="dup-key")
        self.assertEqual(mock_urlopen.call_count, 1)
        send_prospectpilot_event("simulator_started", attribution=attribution, idempotency_key="dup-key")
        self.assertEqual(mock_urlopen.call_count, 1)  # pas de second appel réseau
        self.assertEqual(ProspectPilotOutboundEvent.objects.filter(event_id="dup-key").count(), 1)

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_http_500_is_retryable(self, mock_urlopen):
        from urllib.error import HTTPError
        mock_urlopen.side_effect = HTTPError("url", 500, "err", {}, None)
        attribution = self._attribution()
        event = send_prospectpilot_event("simulator_started", attribution=attribution, idempotency_key="k500")
        self.assertEqual(event.status, "failed")
        self.assertIsNotNone(event.next_retry_at)

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_http_400_is_not_retryable(self, mock_urlopen):
        from urllib.error import HTTPError
        mock_urlopen.side_effect = HTTPError("url", 400, "err", {}, None)
        attribution = self._attribution()
        event = send_prospectpilot_event("simulator_started", attribution=attribution, idempotency_key="k400")
        self.assertEqual(event.status, "dead_letter")

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_network_error_does_not_raise(self, mock_urlopen):
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("boom")
        attribution = self._attribution()
        try:
            event = send_prospectpilot_event("simulator_started", attribution=attribution, idempotency_key="knet")
        except Exception as exc:  # ne doit jamais arriver
            self.fail(f"send_prospectpilot_event a levé une exception : {exc}")
        self.assertEqual(event.status, "failed")

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_no_infinite_retry(self, mock_urlopen):
        mock_urlopen.side_effect = TimeoutError()
        attribution = self._attribution()
        event = send_prospectpilot_event("simulator_started", attribution=attribution, idempotency_key="ktimeout")
        # Simule 10 passages de la commande de retry : une fois en dead_letter,
        # retry_due_events() ne doit plus jamais réessayer (filtre status="failed").
        for _ in range(10):
            ProspectPilotOutboundEvent.objects.filter(pk=event.pk).update(
                next_retry_at=timezone.now() - timezone.timedelta(seconds=1)
            )
            retry_due_events()
        event.refresh_from_db()
        self.assertEqual(event.status, "dead_letter")
        self.assertLessEqual(event.attempt_count, 6)

    def test_card_data_never_included_in_payload(self):
        attribution = self._attribution()
        with patch("predictor.services.prospectpilot_events.urlopen") as mock_urlopen:
            mock_urlopen.return_value = FakeHTTPResponse(200)
            event = send_prospectpilot_event(
                "subscription_activated", attribution=attribution, idempotency_key="kcard",
                card_number="4242424242424242", metadata={"card_number": "4242"},
            )
        self.assertNotIn("card_number", event.payload)
        self.assertNotIn("card_number", event.payload.get("metadata", {}))

    @override_settings(PROSPECTPILOT_EVENTS_ENABLED=False)
    def test_events_disabled_flag_prevents_send(self):
        attribution = self._attribution()
        event = send_prospectpilot_event("simulator_started", attribution=attribution, idempotency_key="kdisabled")
        self.assertEqual(event.status, "dead_letter")


class NoAttributionTests(TestCase):
    def test_user_without_attribution_flows_normally(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        response = self.client.get("/simulateur/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ProspectPilotOutboundEvent.objects.count(), 0)


@override_settings(PROSPECTPILOT_API_URL="https://prospectpilot.example", PROSPECTPILOT_SHARED_SECRET="s3cr3t")
class SimulatorEventTests(TestCase):
    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_get_fires_simulator_started_once(self, mock_urlopen):
        mock_urlopen.return_value = FakeHTTPResponse(200)
        self.client.get("/simulateur/?ppt=simtoken1234567890")
        self.client.get("/simulateur/?ppt=simtoken1234567890")
        started = ProspectPilotOutboundEvent.objects.filter(event_type="simulator_started")
        self.assertEqual(started.count(), 1)

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_post_fires_simulator_completed_with_metadata(self, mock_urlopen):
        mock_urlopen.return_value = FakeHTTPResponse(200)
        self.client.get("/simulateur/?ppt=simtoken2222222222")
        self.client.post("/simulateur/", {"page_visitee": "prix", "temps": "long", "clics": "eleve"})
        completed = ProspectPilotOutboundEvent.objects.get(event_type="simulator_completed")
        self.assertEqual(completed.payload["metadata"]["profil"], "Prêt à acheter")
        self.assertNotIn("temps", completed.payload["metadata"])  # pas de contenu superflu


@override_settings(PROSPECTPILOT_API_URL="https://prospectpilot.example", PROSPECTPILOT_SHARED_SECRET="s3cr3t", STRIPE_SECRET_KEY="sk_test_x")
class SignupEventTests(TestCase):
    @patch("predictor.services.prospectpilot_events.urlopen")
    @patch("predictor.views.create_subscription_checkout_session")
    def test_signup_completed_and_checkout_started_fired(self, mock_checkout, mock_urlopen):
        mock_urlopen.return_value = FakeHTTPResponse(200)
        mock_checkout.return_value = {"id": "cs_test_123", "url": "https://checkout.stripe.com/pay/cs_test_123"}

        self.client.get("/?ppt=signuptoken12345678")
        response = self.client.post("/inscription/", {
            "username": "nouvelleagence",
            "email": "contact@nouvelle-agence.example",
            "password": "un-mot-de-passe-solide",
            "nom_entreprise": "Nouvelle Agence",
            "secteur_activite": "Agence web",
            "nom_site": "nouvelle-agence.example",
            "domaine": "nouvelle-agence.example",
            "accept_conditions": "on",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://checkout.stripe.com/pay/cs_test_123")

        event_types = list(ProspectPilotOutboundEvent.objects.values_list("event_type", flat=True))
        self.assertIn("signup_completed", event_types)
        self.assertIn("checkout_started", event_types)

        attribution = ProspectPilotAttribution.objects.get(token="signuptoken12345678")
        self.assertIsNotNone(attribution.client_professionnel_id)

        # ppt transmis en metadata Stripe pour retrouver l'attribution depuis le webhook.
        mock_checkout.assert_called_once()
        self.assertEqual(mock_checkout.call_args.kwargs.get("ppt_token"), "signuptoken12345678")


@override_settings(PROSPECTPILOT_API_URL="https://prospectpilot.example", PROSPECTPILOT_SHARED_SECRET="s3cr3t", STRIPE_WEBHOOK_SECRET="whsec_test")
class StripeWebhookActivationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="client1", email="client1@example.com", password="x", is_active=False)
        self.client_pro = ClientProfessionnel.objects.create(
            utilisateur=self.user, nom_entreprise="Client Test", statut_abonnement="paiement_en_attente",
        )
        self.attribution = ProspectPilotAttribution.objects.create(
            token="stripetoken1234567", client_professionnel=self.client_pro,
        )

    def _post_webhook(self, event_dict):
        body = json.dumps(event_dict).encode("utf-8")
        with patch("predictor.views.verify_stripe_signature", return_value=True):
            return self.client.post("/stripe/webhook/", data=body, content_type="application/json", HTTP_STRIPE_SIGNATURE="t=1,v1=fake")

    @patch("predictor.services.prospectpilot_events.urlopen")
    @patch("predictor.views.retrieve_subscription")
    def test_checkout_completed_fires_subscription_activated_with_real_price(self, mock_sub, mock_urlopen):
        mock_urlopen.return_value = FakeHTTPResponse(200)
        mock_sub.return_value = {
            "items": {"data": [{"price": {"unit_amount": 9900, "currency": "eur", "recurring": {"interval": "month"}}}]},
        }
        event = {
            "id": "evt_1",
            "type": "checkout.session.completed",
            "data": {"object": {
                "id": "cs_1", "status": "complete", "payment_status": "paid",
                "customer": "cus_1", "subscription": "sub_1",
                "metadata": {"client_id": str(self.client_pro.id)},
                "client_reference_id": str(self.client_pro.id),
            }},
        }
        response = self._post_webhook(event)
        self.assertEqual(response.status_code, 200)
        self.client_pro.refresh_from_db()
        self.assertEqual(self.client_pro.statut_abonnement, "actif")

        activation = ProspectPilotOutboundEvent.objects.get(event_type="subscription_activated")
        self.assertEqual(activation.payload["subscription_value"], 99.0)
        self.assertEqual(activation.payload["mrr"], 99.0)
        self.assertEqual(activation.payload["currency"], "EUR")
        self.assertEqual(activation.payload["external_reference"], "sub_1")

    @patch("predictor.services.prospectpilot_events.urlopen")
    @patch("predictor.views.retrieve_subscription")
    def test_annual_subscription_mrr_normalized(self, mock_sub, mock_urlopen):
        mock_urlopen.return_value = FakeHTTPResponse(200)
        mock_sub.return_value = {
            "items": {"data": [{"price": {"unit_amount": 118800, "currency": "eur", "recurring": {"interval": "year"}}}]},
        }
        event = {
            "id": "evt_2", "type": "checkout.session.completed",
            "data": {"object": {
                "id": "cs_2", "status": "complete", "payment_status": "paid",
                "subscription": "sub_2", "metadata": {"client_id": str(self.client_pro.id)},
            }},
        }
        self._post_webhook(event)
        activation = ProspectPilotOutboundEvent.objects.get(event_type="subscription_activated")
        self.assertEqual(activation.payload["subscription_value"], 1188.0)
        self.assertEqual(activation.payload["mrr"], 99.0)

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_repeated_subscription_updated_does_not_duplicate_activation(self, mock_urlopen):
        mock_urlopen.return_value = FakeHTTPResponse(200)
        self.client_pro.stripe_subscription_id = "sub_3"
        self.client_pro.save()
        event = {
            "id": "evt_3", "type": "customer.subscription.updated",
            "data": {"object": {"id": "sub_3", "customer": "cus_3", "status": "active", "metadata": {}}},
        }
        self._post_webhook(event)
        self._post_webhook({**event, "id": "evt_4"})  # Stripe peut renvoyer plusieurs webhooks
        self.assertEqual(ProspectPilotOutboundEvent.objects.filter(event_type="subscription_activated").count(), 1)

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_subscription_deleted_fires_cancelled_not_activated(self, mock_urlopen):
        mock_urlopen.return_value = FakeHTTPResponse(200)
        self.client_pro.stripe_subscription_id = "sub_4"
        self.client_pro.statut_abonnement = "actif"
        self.client_pro.save()
        event = {
            "id": "evt_5", "type": "customer.subscription.deleted",
            "data": {"object": {"id": "sub_4", "customer": "cus_4", "status": "canceled", "metadata": {}}},
        }
        self._post_webhook(event)
        self.assertTrue(ProspectPilotOutboundEvent.objects.filter(event_type="subscription_cancelled").exists())
        self.assertFalse(ProspectPilotOutboundEvent.objects.filter(event_type="subscription_activated").exists())

    def test_invalid_stripe_signature_rejected(self):
        body = json.dumps({"id": "evt_x", "type": "checkout.session.completed", "data": {"object": {}}}).encode()
        response = self.client.post("/stripe/webhook/", data=body, content_type="application/json", HTTP_STRIPE_SIGNATURE="t=1,v1=bad")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ProspectPilotOutboundEvent.objects.count(), 0)

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_success_page_alone_never_triggers_activation_event(self, mock_urlopen):
        """paiement_succes appelle bien _activate_client_from_checkout_session,
        mais ne doit JAMAIS déclencher l'émission subscription_activated —
        seul le webhook Stripe le fait."""
        mock_urlopen.return_value = FakeHTTPResponse(200)
        with patch("predictor.views.retrieve_checkout_session") as mock_retrieve:
            mock_retrieve.return_value = {
                "id": "cs_5", "status": "complete", "payment_status": "paid",
                "metadata": {"client_id": str(self.client_pro.id)},
            }
            self.client.get("/paiement/succes/?session_id=cs_5")
        self.client_pro.refresh_from_db()
        self.assertEqual(self.client_pro.statut_abonnement, "actif")  # le compte est bien activé...
        self.assertFalse(ProspectPilotOutboundEvent.objects.filter(event_type="subscription_activated").exists())  # ...mais sans notification


class NoSecretLeakTests(TestCase):
    @override_settings(PROSPECTPILOT_API_URL="https://prospectpilot.example", PROSPECTPILOT_SHARED_SECRET="s3cr3t-value")
    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_secret_never_in_stored_payload(self, mock_urlopen):
        mock_urlopen.return_value = FakeHTTPResponse(200)
        attribution = ProspectPilotAttribution.objects.create(token="secretcheck1234567")
        event = send_prospectpilot_event("simulator_started", attribution=attribution, idempotency_key="ksecret")
        self.assertNotIn("s3cr3t-value", json.dumps(event.payload))

    def test_admin_view_does_not_expose_secret_field(self):
        from predictor.admin import ProspectPilotOutboundEventAdmin
        self.assertNotIn("PROSPECTPILOT_SHARED_SECRET", str(ProspectPilotOutboundEventAdmin.list_display))
