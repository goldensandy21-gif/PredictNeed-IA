from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import signing
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from .connector_oauth_flows import (
    charger_flux_selection_compte,
    creer_flux_selection_compte,
    upsert_compte_selectionne,
)
from .external_connectors import (
    lire_token_signe,
    signer_token,
    token_stocke_est_chiffre,
)
from .models import ClientProfessionnel, CompteConnecteExterne, SiteClient


FAKE_CONNECTORS = {
    "google_ads": {
        "nom": "Google Ads",
        "description": "Test Google Ads",
        "client_id": "client-test",
        "client_secret": "secret-test",
        "developer_token": "developer-token-test",
        "auth_url": "https://accounts.example.test/auth",
        "token_url": "https://accounts.example.test/token",
        "scopes": ["https://www.googleapis.com/auth/adwords"],
        "variables_requises": [],
        "variables_optionnelles": [],
    },
}


@override_settings(PREDICTNEED_EXTERNAL_CONNECTORS=FAKE_CONNECTORS)
class ConnectorOAuthFlowTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="flow-owner",
            email="flow-owner@example.com",
            password="MotDePasse-Solide-2026!",
        )
        self.other_user = User.objects.create_user(
            username="flow-other",
            email="flow-other@example.com",
            password="MotDePasse-Solide-2026!",
        )
        self.client_pro = ClientProfessionnel.objects.create(
            utilisateur=self.user,
            nom_entreprise="Flow Corp",
            statut_abonnement="actif",
        )
        self.site = SiteClient.objects.create(
            client=self.client_pro,
            nom_site="Site Flow",
            domaine="flow.example",
            actif=True,
            module_connecteurs_actif=True,
        )
        self.client.force_login(self.user)
        self.factory = RequestFactory()

    def _request(self, session=None):
        request = self.factory.get("/")
        request.user = self.user
        request.session = session or self.client.session
        return request

    def test_creating_flow_prunes_expired_entries(self):
        session = self.client.session
        session["google_ads_oauth_flows"] = {
            "expired": {
                "user_id": self.user.id,
                "client_id": self.client_pro.id,
                "site_id": self.site.id,
                "created_at": (
                    timezone.now()
                    - timedelta(minutes=16)
                ).timestamp(),
                "comptes": [],
            }
        }
        session.save()

        flow_id = creer_flux_selection_compte(
            self._request(session),
            "google_ads",
            client=self.client_pro,
            site=self.site,
            access_token="access",
            refresh_token="refresh",
            token_payload={"token_type": "Bearer", "expires_in": 3600},
            comptes=[{"customer_id": "123"}],
        )

        flows = session["google_ads_oauth_flows"]
        self.assertNotIn("expired", flows)
        self.assertIn(flow_id, flows)

    def test_flow_rejects_wrong_user_and_removes_entry(self):
        session = self.client.session
        session["google_ads_oauth_flows"] = {
            "flow": {
                "user_id": self.other_user.id,
                "client_id": self.client_pro.id,
                "site_id": self.site.id,
                "created_at": timezone.now().timestamp(),
                "comptes": [],
            }
        }
        session.save()

        request = self._request(session)

        flux = charger_flux_selection_compte(
            request,
            "google_ads",
            "flow",
            self.client_pro,
        )

        self.assertFalse(flux["ok"])
        self.assertEqual(
            request.session["google_ads_oauth_flows"],
            {},
        )

    def test_upsert_preserves_existing_refresh_token_when_pending_has_none(self):
        existing = CompteConnecteExterne.objects.create(
            client=self.client_pro,
            site=self.site,
            plateforme="google_ads",
            identifiant_externe="123",
            nom_compte="Ancien compte",
            refresh_token_signe=signer_token("old-refresh"),
        )
        old_refresh = existing.refresh_token_signe

        compte, created = upsert_compte_selectionne(
            client=self.client_pro,
            site=self.site,
            plateforme="google_ads",
            identifiant_externe="123",
            nom_compte="Compte mis à jour",
            pending={
                "access_token_signe": signer_token("new-access"),
                "refresh_token_signe": "",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
            configuration={"source": "test"},
            dernier_message="Compte prêt.",
        )

        self.assertFalse(created)
        compte.refresh_from_db()
        self.assertEqual(compte.refresh_token_signe, old_refresh)
        self.assertEqual(compte.nom_compte, "Compte mis à jour")

    @override_settings(
        PREDICTNEED_TOKEN_ENCRYPTION_KEY="unit-test-token-encryption-key"
    )
    def test_tokens_are_encrypted_when_key_is_configured_and_legacy_is_readable(self):
        legacy_signed = signing.dumps(
            "legacy-token",
            salt="predictneed-connecteur-token",
        )

        encrypted = signer_token("secret-token")

        self.assertTrue(token_stocke_est_chiffre(encrypted))
        self.assertNotIn("secret-token", encrypted)
        self.assertEqual(lire_token_signe(encrypted), "secret-token")
        self.assertEqual(lire_token_signe(legacy_signed), "legacy-token")
