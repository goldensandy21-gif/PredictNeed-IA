from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import signing
from django.test import TestCase, override_settings
from django.utils import timezone

from .google_ads_api import (
    GoogleAdsConfigurationError,
    access_token_pour_compte,
    decouvrir_comptes_publicitaires,
    lister_comptes_accessibles,
    normaliser_customer_id,
    rechercher,
)
from .models import (
    ClientProfessionnel,
    CompteConnecteExterne,
    SiteClient,
)


FAKE_CONNECTORS = {
    "google_ads": {
        "nom": "Google Ads",
        "description": "Test Google Ads",
        "client_id": "client-test",
        "client_secret": "secret-test",
        "developer_token": "developer-token-test",
        "login_customer_id": "",
        "api_version": "v25",
        "auth_url": "https://accounts.example.test/auth",
        "token_url": "https://accounts.example.test/token",
        "scopes": [
            "https://www.googleapis.com/auth/adwords",
        ],
    },
}


@override_settings(
    PREDICTNEED_EXTERNAL_CONNECTORS=FAKE_CONNECTORS,
)
class GoogleAdsAPITests(TestCase):

    def test_normalise_customer_id(self):
        self.assertEqual(
            normaliser_customer_id("123-456-7890"),
            "1234567890",
        )

        with self.assertRaises(ValueError):
            normaliser_customer_id("1234")

    @patch("predictor.google_ads_api._request_json")
    def test_list_accessible_customers_parses_resource_names(
        self,
        request_json,
    ):
        request_json.return_value = {
            "resourceNames": [
                "customers/1234567890",
                "customers/2223334444",
                "customers/1234567890",
                "invalid/value",
            ]
        }

        result = lister_comptes_accessibles(
            "access-token-test"
        )

        self.assertEqual(
            result,
            [
                "1234567890",
                "2223334444",
            ],
        )

        kwargs = request_json.call_args.kwargs

        self.assertIn(
            "developer-token",
            kwargs["headers"],
        )
        self.assertEqual(
            kwargs["headers"]["Authorization"],
            "Bearer access-token-test",
        )

    @patch("predictor.google_ads_api._request_json")
    def test_search_paginates_and_uses_login_customer_id(
        self,
        request_json,
    ):
        request_json.side_effect = [
            {
                "results": [{"campaign": {"id": "1"}}],
                "nextPageToken": "page-2",
            },
            {
                "results": [{"campaign": {"id": "2"}}],
            },
        ]

        rows = rechercher(
            "access-token-test",
            "1112223333",
            "SELECT campaign.id FROM campaign",
            login_customer_id="999-888-7777",
        )

        self.assertEqual(
            [row["campaign"]["id"] for row in rows],
            ["1", "2"],
        )

        self.assertEqual(
            request_json.call_count,
            2,
        )

        first_call = request_json.call_args_list[0]
        second_call = request_json.call_args_list[1]

        self.assertEqual(
            first_call.kwargs["headers"]["login-customer-id"],
            "9998887777",
        )
        self.assertNotIn(
            "pageToken",
            first_call.kwargs["payload"],
        )
        self.assertEqual(
            second_call.kwargs["payload"]["pageToken"],
            "page-2",
        )

    @patch("predictor.google_ads_api._enfants_manager")
    @patch("predictor.google_ads_api.decrire_compte")
    @patch("predictor.google_ads_api.lister_comptes_accessibles")
    def test_discovery_excludes_managers_and_keeps_login_manager(
        self,
        accessible,
        describe,
        children,
    ):
        accessible.return_value = [
            "1111111111",
            "2222222222",
        ]

        describe.side_effect = [
            {
                "customer_id": "1111111111",
                "nom": "Manager principal",
                "devise": "EUR",
                "fuseau_horaire": "Europe/Paris",
                "manager": True,
                "test_account": False,
                "statut": "ENABLED",
                "login_customer_id": "",
            },
            {
                "customer_id": "2222222222",
                "nom": "Compte direct",
                "devise": "EUR",
                "fuseau_horaire": "Europe/Paris",
                "manager": False,
                "test_account": False,
                "statut": "ENABLED",
                "login_customer_id": "",
            },
        ]

        children.return_value = [
            {
                "customer_id": "3333333333",
                "nom": "Compte client",
                "devise": "EUR",
                "fuseau_horaire": "Europe/Paris",
                "manager": False,
                "test_account": False,
                "statut": "ENABLED",
                "login_customer_id": "1111111111",
            }
        ]

        result = decouvrir_comptes_publicitaires(
            "access-token-test"
        )

        self.assertSetEqual(
            {item["customer_id"] for item in result},
            {
                "2222222222",
                "3333333333",
            },
        )

        managed = next(
            item
            for item in result
            if item["customer_id"] == "3333333333"
        )

        self.assertEqual(
            managed["login_customer_id"],
            "1111111111",
        )

    @override_settings(
        PREDICTNEED_EXTERNAL_CONNECTORS={
            "google_ads": {
                "client_id": "client",
                "client_secret": "secret",
                "developer_token": "",
                "api_version": "v25",
            }
        }
    )
    def test_missing_developer_token_is_rejected(self):
        with self.assertRaises(
            GoogleAdsConfigurationError
        ):
            lister_comptes_accessibles(
                "access-token-test"
            )

    @patch("predictor.google_ads_api.rafraichir_access_token")
    def test_expired_access_token_is_refreshed_and_saved(
        self,
        refresh_access_token,
    ):
        User = get_user_model()

        user = User.objects.create_user(
            username="google-refresh",
            email="google-refresh@example.com",
            password="MotDePasse-Solide-2026!",
        )

        client_pro = ClientProfessionnel.objects.create(
            utilisateur=user,
            nom_entreprise="Entreprise Google",
            statut_abonnement="actif",
        )

        site = SiteClient.objects.create(
            client=client_pro,
            nom_site="Google Site",
            domaine="google.example",
            actif=True,
        )

        account = CompteConnecteExterne.objects.create(
            client=client_pro,
            site=site,
            plateforme="google_ads",
            nom_compte="Google Ads",
            identifiant_externe="1234567890",
            statut="connecte",
            access_token_signe=signing.dumps(
                "old-token",
                salt="predictneed-connecteur-token",
            ),
            refresh_token_signe=signing.dumps(
                "refresh-token",
                salt="predictneed-connecteur-token",
            ),
            expires_at=timezone.now() - timedelta(minutes=5),
        )

        refresh_access_token.return_value = {
            "access_token": "new-token",
            "expires_in": 3600,
        }

        token = access_token_pour_compte(account)

        self.assertEqual(token, "new-token")

        account.refresh_from_db()

        self.assertEqual(
            signing.loads(
                account.access_token_signe,
                salt="predictneed-connecteur-token",
            ),
            "new-token",
        )
        self.assertGreater(
            account.expires_at,
            timezone.now(),
        )

    @patch("predictor.google_ads_api.rafraichir_access_token")
    def test_valid_access_token_is_reused_without_refresh(
        self,
        refresh_access_token,
    ):
        User = get_user_model()

        user = User.objects.create_user(
            username="google-valid",
            email="google-valid@example.com",
            password="MotDePasse-Solide-2026!",
        )

        client_pro = ClientProfessionnel.objects.create(
            utilisateur=user,
            nom_entreprise="Entreprise Google valide",
            statut_abonnement="actif",
        )

        site = SiteClient.objects.create(
            client=client_pro,
            nom_site="Google Site valide",
            domaine="google-valid.example",
            actif=True,
        )

        account = CompteConnecteExterne.objects.create(
            client=client_pro,
            site=site,
            plateforme="google_ads",
            nom_compte="Google Ads",
            identifiant_externe="1234567890",
            statut="connecte",
            access_token_signe=signing.dumps(
                "valid-token",
                salt="predictneed-connecteur-token",
            ),
            refresh_token_signe=signing.dumps(
                "refresh-token",
                salt="predictneed-connecteur-token",
            ),
            expires_at=timezone.now() + timedelta(hours=1),
        )

        token = access_token_pour_compte(account)

        self.assertEqual(token, "valid-token")
        refresh_access_token.assert_not_called()
