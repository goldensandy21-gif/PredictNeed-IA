"""Tests de l'intégration ProspectPilot <-> PredictNeed IA.

Architecture testée : send_prospectpilot_event() est un enqueue pur (aucune
E/S réseau) ; seul retry_due_events() (appelé par la commande de gestion
retry_prospectpilot_events, hors requête utilisateur) contacte réellement
ProspectPilot.
"""
import json
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from predictor.models import (
    ClientProfessionnel,
    ProspectPilotAttribution,
    ProspectPilotOutboundEvent,
)
from predictor.services.prospectpilot_attribution import (
    capture_prospectpilot_attribution,
    get_current_attribution,
)
from predictor.services.prospectpilot_events import (
    _eligible_filter,
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
        self.client.get("/?ppt=" + "abc def<script>")
        self.assertEqual(ProspectPilotAttribution.objects.count(), 0)

    def test_attribution_kept_in_session_across_requests(self):
        self.client.get("/?ppt=firsttouchtoken123")
        response = self.client.get("/fonctionnalites/")
        self.assertEqual(response.status_code, 200)
        session = self.client.session
        self.assertIn("prospectpilot_attribution_id", session)

    def test_first_touch_not_overwritten_by_second_token(self):
        self.client.get("/?ppt=firsttouchtoken123")
        first_id = self.client.session["prospectpilot_attribution_id"]
        self.client.get("/?ppt=secondtouchtoken456")
        second_id = self.client.session["prospectpilot_attribution_id"]
        self.assertEqual(first_id, second_id)
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


class NoAttributionTests(TestCase):
    def test_user_without_attribution_flows_normally(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/simulateur/").status_code, 200)
        self.assertEqual(ProspectPilotOutboundEvent.objects.count(), 0)


# ---------------------------------------------------------------------------
# 1. send_prospectpilot_event() est un enqueue pur — aucun appel réseau.
# ---------------------------------------------------------------------------

class EnqueueOnlyTests(TestCase):
    def _attribution(self):
        return ProspectPilotAttribution.objects.create(token="tok1234567890abcd")

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_send_event_makes_no_http_call(self, mock_urlopen):
        attribution = self._attribution()
        event = send_prospectpilot_event("simulator_started", attribution=attribution, idempotency_key="k1")
        mock_urlopen.assert_not_called()
        self.assertEqual(event.status, "pending")
        self.assertEqual(event.attempt_count, 0)

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_duplicate_idempotency_key_returns_same_row_no_http(self, mock_urlopen):
        attribution = self._attribution()
        send_prospectpilot_event("simulator_started", attribution=attribution, idempotency_key="dup-key")
        send_prospectpilot_event("simulator_started", attribution=attribution, idempotency_key="dup-key")
        mock_urlopen.assert_not_called()
        self.assertEqual(ProspectPilotOutboundEvent.objects.filter(event_id="dup-key").count(), 1)

    def test_card_data_never_included_in_payload(self):
        attribution = self._attribution()
        event = send_prospectpilot_event(
            "subscription_activated", attribution=attribution, idempotency_key="kcard",
            card_number="4242424242424242", metadata={"card_number": "4242"},
        )
        self.assertNotIn("card_number", event.payload)
        self.assertNotIn("card_number", event.payload.get("metadata", {}))

    @override_settings(PROSPECTPILOT_API_URL="https://prospectpilot.example", PROSPECTPILOT_SHARED_SECRET="s3cr3t")
    def test_idempotency_key_unchanged_through_retry(self):
        attribution = self._attribution()
        event = send_prospectpilot_event("simulator_started", attribution=attribution, idempotency_key="kstable")
        original_event_id = event.event_id
        with patch("predictor.services.prospectpilot_events.urlopen") as mock_urlopen:
            mock_urlopen.return_value = FakeHTTPResponse(200)
            retry_due_events()
        event.refresh_from_db()
        self.assertEqual(event.event_id, original_event_id)
        self.assertEqual(event.status, "sent")


@override_settings(PROSPECTPILOT_API_URL="https://prospectpilot.example", PROSPECTPILOT_SHARED_SECRET="s3cr3t")
class RetryDeliveryOutcomeTests(TestCase):
    def _pending_event(self, key="k1"):
        attribution = ProspectPilotAttribution.objects.create(token=f"tok-{key}-1234567890")
        return send_prospectpilot_event("simulator_started", attribution=attribution, idempotency_key=key)

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_pending_becomes_sent_after_success(self, mock_urlopen):
        mock_urlopen.return_value = FakeHTTPResponse(200)
        event = self._pending_event()
        result = retry_due_events()
        event.refresh_from_db()
        self.assertEqual(event.status, "sent")
        self.assertEqual(result["sent"], 1)
        self.assertEqual(event.attempt_count, 1)

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_timeout_becomes_failed(self, mock_urlopen):
        mock_urlopen.side_effect = TimeoutError()
        event = self._pending_event()
        retry_due_events()
        event.refresh_from_db()
        self.assertEqual(event.status, "failed")
        self.assertIsNotNone(event.next_retry_at)

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_http_500_becomes_failed(self, mock_urlopen):
        from urllib.error import HTTPError
        mock_urlopen.side_effect = HTTPError("url", 500, "err", {}, None)
        event = self._pending_event()
        retry_due_events()
        event.refresh_from_db()
        self.assertEqual(event.status, "failed")

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_http_429_becomes_failed_for_retry(self, mock_urlopen):
        from urllib.error import HTTPError
        mock_urlopen.side_effect = HTTPError("url", 429, "err", {}, None)
        event = self._pending_event()
        retry_due_events()
        event.refresh_from_db()
        self.assertEqual(event.status, "failed")
        self.assertIsNotNone(event.next_retry_at)

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_http_400_becomes_dead_letter(self, mock_urlopen):
        from urllib.error import HTTPError
        mock_urlopen.side_effect = HTTPError("url", 400, "err", {}, None)
        event = self._pending_event()
        retry_due_events()
        event.refresh_from_db()
        self.assertEqual(event.status, "dead_letter")

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_http_401_with_real_configuration_becomes_dead_letter(self, mock_urlopen):
        from urllib.error import HTTPError
        mock_urlopen.side_effect = HTTPError("url", 401, "err", {}, None)
        event = self._pending_event()
        retry_due_events()
        event.refresh_from_db()
        self.assertEqual(event.status, "dead_letter")

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_network_error_does_not_raise_and_becomes_failed(self, mock_urlopen):
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("boom")
        event = self._pending_event()
        try:
            retry_due_events()
        except Exception as exc:
            self.fail(f"retry_due_events a levé une exception : {exc}")
        event.refresh_from_db()
        self.assertEqual(event.status, "failed")

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_no_infinite_retry(self, mock_urlopen):
        mock_urlopen.side_effect = TimeoutError()
        event = self._pending_event()
        # On ne force QUE next_retry_at dans le passé (simule "le temps a
        # passé") — jamais le statut : une fois dead_letter, l'événement doit
        # sortir naturellement du filtre d'éligibilité et ne plus être touché.
        for _ in range(10):
            ProspectPilotOutboundEvent.objects.filter(pk=event.pk).update(
                next_retry_at=timezone.now() - timezone.timedelta(seconds=1)
            )
            retry_due_events()
        event.refresh_from_db()
        self.assertEqual(event.status, "dead_letter")
        self.assertLessEqual(event.attempt_count, 6)

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_dry_run_makes_no_http_call_and_no_state_change(self, mock_urlopen):
        event = self._pending_event()
        result = retry_due_events(dry_run=True)
        mock_urlopen.assert_not_called()
        event.refresh_from_db()
        self.assertEqual(event.status, "pending")
        self.assertEqual(result["would_process"], 1)
        self.assertIn(event.pk, result["event_ids"])

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_limit_caps_number_processed(self, mock_urlopen):
        mock_urlopen.return_value = FakeHTTPResponse(200)
        for i in range(5):
            self._pending_event(key=f"limit-{i}")
        result = retry_due_events(limit=2)
        self.assertEqual(result["attempted"], 2)
        self.assertEqual(ProspectPilotOutboundEvent.objects.filter(status="pending").count(), 3)

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_events_are_delivered_in_chronological_order(self, mock_urlopen):
        """Régression : la ré-vérification après réclamation n'a pas d'ordre
        garanti — sans tri explicite, des événements comme signup_completed
        et subscription_activated peuvent partir dans le désordre et inverser
        une transition de statut côté ProspectPilot."""
        delivered_order = []

        def record_order(request, timeout=None):
            payload = json.loads(request.data.decode("utf-8"))
            delivered_order.append(payload["event_type"])
            return FakeHTTPResponse(200)

        mock_urlopen.side_effect = record_order

        attribution = ProspectPilotAttribution.objects.create(token="ordertoken1234567890")
        for event_type in ["simulator_started", "signup_completed", "checkout_started", "subscription_activated"]:
            send_prospectpilot_event(event_type, attribution=attribution, idempotency_key=f"order:{event_type}")

        retry_due_events()
        self.assertEqual(
            delivered_order,
            ["simulator_started", "signup_completed", "checkout_started", "subscription_activated"],
        )


# ---------------------------------------------------------------------------
# 3. Absence de configuration locale != erreur serveur.
# ---------------------------------------------------------------------------

class MissingConfigurationTests(TestCase):
    def _pending_event(self, key="cfg1"):
        attribution = ProspectPilotAttribution.objects.create(token=f"tok-{key}-1234567890")
        return send_prospectpilot_event("simulator_started", attribution=attribution, idempotency_key=key)

    @override_settings(PROSPECTPILOT_API_URL="", PROSPECTPILOT_SHARED_SECRET="s3cr3t")
    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_missing_api_url_never_dead_letters(self, mock_urlopen):
        event = self._pending_event("no-url")
        retry_due_events()
        mock_urlopen.assert_not_called()
        event.refresh_from_db()
        self.assertEqual(event.status, "pending_config")
        self.assertEqual(event.attempt_count, 0)

    @override_settings(PROSPECTPILOT_API_URL="https://prospectpilot.example", PROSPECTPILOT_SHARED_SECRET="")
    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_missing_secret_never_dead_letters(self, mock_urlopen):
        event = self._pending_event("no-secret")
        retry_due_events()
        mock_urlopen.assert_not_called()
        event.refresh_from_db()
        self.assertEqual(event.status, "pending_config")

    @override_settings(PROSPECTPILOT_EVENTS_ENABLED=False, PROSPECTPILOT_API_URL="https://prospectpilot.example", PROSPECTPILOT_SHARED_SECRET="s3cr3t")
    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_events_disabled_does_not_lose_event(self, mock_urlopen):
        event = self._pending_event("disabled")
        retry_due_events()
        mock_urlopen.assert_not_called()
        event.refresh_from_db()
        self.assertEqual(event.status, "pending_config")
        self.assertIsNotNone(ProspectPilotOutboundEvent.objects.get(pk=event.pk))  # jamais supprimé

    @override_settings(PROSPECTPILOT_API_URL="", PROSPECTPILOT_SHARED_SECRET="")
    def test_pending_config_never_reaches_dead_letter_even_after_many_retries(self):
        event = self._pending_event("never-dead")
        for _ in range(20):
            retry_due_events()
        event.refresh_from_db()
        self.assertEqual(event.status, "pending_config")
        self.assertEqual(event.attempt_count, 0)

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_config_fixed_later_allows_send(self, mock_urlopen):
        with override_settings(PROSPECTPILOT_API_URL="", PROSPECTPILOT_SHARED_SECRET=""):
            event = self._pending_event("fixed-later")
            retry_due_events()
        event.refresh_from_db()
        self.assertEqual(event.status, "pending_config")

        mock_urlopen.return_value = FakeHTTPResponse(200)
        with override_settings(PROSPECTPILOT_API_URL="https://prospectpilot.example", PROSPECTPILOT_SHARED_SECRET="s3cr3t"):
            retry_due_events()
        event.refresh_from_db()
        self.assertEqual(event.status, "sent")


# ---------------------------------------------------------------------------
# 2. Récupération des "sending" orphelins + sûreté concurrente.
# ---------------------------------------------------------------------------

@override_settings(PROSPECTPILOT_API_URL="https://prospectpilot.example", PROSPECTPILOT_SHARED_SECRET="s3cr3t")
class StaleSendingRecoveryTests(TestCase):
    def _pending_event(self, key="stale1"):
        attribution = ProspectPilotAttribution.objects.create(token=f"tok-{key}-1234567890")
        return send_prospectpilot_event("simulator_started", attribution=attribution, idempotency_key=key)

    @override_settings(PROSPECTPILOT_STALE_SENDING_SECONDS=600)
    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_recent_sending_not_picked_up(self, mock_urlopen):
        event = self._pending_event("recent")
        event.status = "sending"
        event.last_attempt_at = timezone.now() - timezone.timedelta(seconds=30)
        event.save(update_fields=["status", "last_attempt_at"])

        result = retry_due_events()
        mock_urlopen.assert_not_called()
        self.assertEqual(result["claimed"], 0)
        event.refresh_from_db()
        self.assertEqual(event.status, "sending")

    @override_settings(PROSPECTPILOT_STALE_SENDING_SECONDS=600)
    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_old_sending_is_recovered_and_retried(self, mock_urlopen):
        mock_urlopen.return_value = FakeHTTPResponse(200)
        event = self._pending_event("stale")
        # Simule un crash du runner juste après avoir réclamé l'événement.
        event.status = "sending"
        event.last_attempt_at = timezone.now() - timezone.timedelta(seconds=900)
        event.save(update_fields=["status", "last_attempt_at"])

        result = retry_due_events()
        self.assertEqual(result["claimed"], 1)
        event.refresh_from_db()
        self.assertEqual(event.status, "sent")

    def test_double_claim_is_prevented_by_conditional_update(self):
        """Preuve déterministe (sans dépendre d'un vrai thread-race, non fiable
        à tester) que deux tentatives de réclamation de la même ligne ne
        peuvent pas réussir toutes les deux : la seconde UPDATE conditionnelle
        ne matche plus rien une fois le statut changé par la première."""
        event = self._pending_event("race")
        now = timezone.now()
        stale_cutoff = now - timezone.timedelta(seconds=600)
        base_filter = _eligible_filter(now, stale_cutoff)

        claimed_by_worker_a = ProspectPilotOutboundEvent.objects.filter(
            base_filter, pk=event.pk
        ).update(status="sending", last_attempt_at=now)
        claimed_by_worker_b = ProspectPilotOutboundEvent.objects.filter(
            base_filter, pk=event.pk
        ).update(status="sending", last_attempt_at=now)

        self.assertEqual(claimed_by_worker_a, 1)
        self.assertEqual(claimed_by_worker_b, 0)

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_concurrent_runs_do_not_duplicate_revenue_attribution(self, mock_urlopen):
        """Deux passages successifs de retry_due_events() sur le même
        événement subscription_activated ne doivent produire qu'un seul envoi
        (la seconde exécution ne trouve plus rien à réclamer)."""
        mock_urlopen.return_value = FakeHTTPResponse(200)
        attribution = ProspectPilotAttribution.objects.create(token="revenuetoken1234567")
        send_prospectpilot_event(
            "subscription_activated", attribution=attribution, idempotency_key="subscription:sub_race:activated",
            subscription_value=99.0, mrr=99.0, currency="EUR", external_reference="sub_race",
        )
        result_a = retry_due_events()
        result_b = retry_due_events()
        self.assertEqual(result_a["sent"], 1)
        self.assertEqual(result_b["claimed"], 0)
        self.assertEqual(mock_urlopen.call_count, 1)


# ---------------------------------------------------------------------------
# Vues métier : aucun appel réseau, uniquement un enqueue.
# ---------------------------------------------------------------------------

@override_settings(PROSPECTPILOT_API_URL="https://prospectpilot.example", PROSPECTPILOT_SHARED_SECRET="s3cr3t")
class SimulatorEventTests(TestCase):
    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_get_enqueues_simulator_started_once_no_http(self, mock_urlopen):
        self.client.get("/simulateur/?ppt=simtoken1234567890")
        self.client.get("/simulateur/?ppt=simtoken1234567890")
        mock_urlopen.assert_not_called()
        started = ProspectPilotOutboundEvent.objects.filter(event_type="simulator_started")
        self.assertEqual(started.count(), 1)
        self.assertEqual(started.first().status, "pending")

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_post_enqueues_simulator_completed_with_metadata_no_http(self, mock_urlopen):
        self.client.get("/simulateur/?ppt=simtoken2222222222")
        self.client.post("/simulateur/", {"page_visitee": "prix", "temps": "long", "clics": "eleve"})
        mock_urlopen.assert_not_called()
        completed = ProspectPilotOutboundEvent.objects.get(event_type="simulator_completed")
        self.assertEqual(completed.status, "pending")
        self.assertEqual(completed.payload["metadata"]["profil"], "Prêt à acheter")
        self.assertNotIn("temps", completed.payload["metadata"])


@override_settings(PROSPECTPILOT_API_URL="https://prospectpilot.example", PROSPECTPILOT_SHARED_SECRET="s3cr3t", STRIPE_SECRET_KEY="sk_test_x")
class SignupEventTests(TestCase):
    @patch("predictor.services.prospectpilot_events.urlopen")
    @patch("predictor.views.create_subscription_checkout_session")
    def test_signup_and_checkout_enqueued_no_http(self, mock_checkout, mock_urlopen):
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
        mock_urlopen.assert_not_called()  # ni product_visited, ni signup_completed, ni checkout_started

        event_types = list(ProspectPilotOutboundEvent.objects.values_list("event_type", "status"))
        self.assertIn(("signup_completed", "pending"), event_types)
        self.assertIn(("checkout_started", "pending"), event_types)

        attribution = ProspectPilotAttribution.objects.get(token="signuptoken12345678")
        self.assertIsNotNone(attribution.client_professionnel_id)
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
    def test_webhook_enqueues_activation_without_any_http_call(self, mock_urlopen):
        event = {
            "id": "evt_1", "type": "checkout.session.completed",
            "data": {"object": {
                "id": "cs_1", "status": "complete", "payment_status": "paid",
                "customer": "cus_1", "subscription": "sub_1",
                "metadata": {"client_id": str(self.client_pro.id)},
                "client_reference_id": str(self.client_pro.id),
            }},
        }
        response = self._post_webhook(event)
        self.assertEqual(response.status_code, 200)
        mock_urlopen.assert_not_called()  # ni le prix Stripe réel, ni ProspectPilot

        self.client_pro.refresh_from_db()
        self.assertEqual(self.client_pro.statut_abonnement, "actif")
        activation = ProspectPilotOutboundEvent.objects.get(event_type="subscription_activated")
        self.assertEqual(activation.status, "pending")
        # Le prix réel n'a pas pu être récupéré (aucun appel Stripe fait ici) :
        # subscription_value/mrr restent absents, ce qui est correct — c'est
        # le futur retry_due_events, pas le webhook, qui doit rester rapide.
        # (Le calcul du prix réel a lieu de façon synchrone AU MOMENT DU WEBHOOK
        # avant l'enqueue, cf. _notify_subscription_activated — vérifié ci-dessous.)

    @patch("predictor.services.prospectpilot_events.urlopen")
    @patch("predictor.views.retrieve_subscription")
    def test_annual_subscription_mrr_normalized_in_enqueued_payload(self, mock_sub, mock_urlopen):
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
        mock_urlopen.assert_not_called()
        activation = ProspectPilotOutboundEvent.objects.get(event_type="subscription_activated")
        self.assertEqual(activation.payload["subscription_value"], 1188.0)
        self.assertEqual(activation.payload["mrr"], 99.0)

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_repeated_subscription_updated_does_not_duplicate_activation_event(self, mock_urlopen):
        self.client_pro.stripe_subscription_id = "sub_3"
        self.client_pro.save()
        event = {
            "id": "evt_3", "type": "customer.subscription.updated",
            "data": {"object": {"id": "sub_3", "customer": "cus_3", "status": "active", "metadata": {}}},
        }
        self._post_webhook(event)
        self._post_webhook({**event, "id": "evt_4"})
        mock_urlopen.assert_not_called()
        self.assertEqual(ProspectPilotOutboundEvent.objects.filter(event_type="subscription_activated").count(), 1)

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_subscription_deleted_enqueues_cancelled_not_activated(self, mock_urlopen):
        self.client_pro.stripe_subscription_id = "sub_4"
        self.client_pro.statut_abonnement = "actif"
        self.client_pro.save()
        event = {
            "id": "evt_5", "type": "customer.subscription.deleted",
            "data": {"object": {"id": "sub_4", "customer": "cus_4", "status": "canceled", "metadata": {}}},
        }
        self._post_webhook(event)
        mock_urlopen.assert_not_called()
        self.assertTrue(ProspectPilotOutboundEvent.objects.filter(event_type="subscription_cancelled").exists())
        self.assertFalse(ProspectPilotOutboundEvent.objects.filter(event_type="subscription_activated").exists())

    def test_invalid_stripe_signature_rejected(self):
        body = json.dumps({"id": "evt_x", "type": "checkout.session.completed", "data": {"object": {}}}).encode()
        response = self.client.post("/stripe/webhook/", data=body, content_type="application/json", HTTP_STRIPE_SIGNATURE="t=1,v1=bad")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ProspectPilotOutboundEvent.objects.count(), 0)

    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_success_page_alone_never_triggers_activation_event(self, mock_urlopen):
        with patch("predictor.views.retrieve_checkout_session") as mock_retrieve:
            mock_retrieve.return_value = {
                "id": "cs_5", "status": "complete", "payment_status": "paid",
                "metadata": {"client_id": str(self.client_pro.id)},
            }
            self.client.get("/paiement/succes/?session_id=cs_5")
        mock_urlopen.assert_not_called()
        self.client_pro.refresh_from_db()
        self.assertEqual(self.client_pro.statut_abonnement, "actif")
        self.assertFalse(ProspectPilotOutboundEvent.objects.filter(event_type="subscription_activated").exists())


class NoSecretLeakTests(TestCase):
    @override_settings(PROSPECTPILOT_API_URL="https://prospectpilot.example", PROSPECTPILOT_SHARED_SECRET="s3cr3t-value")
    @patch("predictor.services.prospectpilot_events.urlopen")
    def test_secret_never_in_stored_payload(self, mock_urlopen):
        mock_urlopen.return_value = FakeHTTPResponse(200)
        attribution = ProspectPilotAttribution.objects.create(token="secretcheck1234567")
        event = send_prospectpilot_event("simulator_started", attribution=attribution, idempotency_key="ksecret")
        retry_due_events()
        event.refresh_from_db()
        self.assertNotIn("s3cr3t-value", json.dumps(event.payload))

    def test_admin_view_does_not_expose_secret_field(self):
        from predictor.admin import ProspectPilotOutboundEventAdmin
        self.assertNotIn("PROSPECTPILOT_SHARED_SECRET", str(ProspectPilotOutboundEventAdmin.list_display))
