from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from .external_connectors import (
    construire_url_autorisation,
    lire_token_signe,
    signer_token,
)
from .models import (
    ClientProfessionnel,
    CompteConnecteExterne,
    SiteClient,
)
from .tiktok_ads_api import (
    TikTokAdsConfigurationError,
    _configuration_tiktok_ads,
    access_token_pour_compte_tiktok,
    echanger_code_contre_token_tiktok,
    lister_campagnes_tiktok,
    lister_comptes_publicitaires_tiktok,
    lister_performances_campagnes_tiktok,
    normaliser_advertiser_id,
)


FAKE_CONNECTORS = {
    "tiktok_ads": {
        "nom": "TikTok Ads",
        "description": "Test TikTok Ads",
        "client_id": "app-id",
        "client_secret": "secret",
        "api_version": "v1.3",
        "base_url": "https://business-api.tiktok.com/open_api",
        "auth_url": "https://ads.tiktok.com/marketing_api/auth",
        "token_url": (
            "https://business-api.tiktok.com/open_api/"
            "v1.3/oauth2/access_token/"
        ),
        "scopes": ["scope.a", "scope.b"],
    },
}


@override_settings(
    PREDICTNEED_EXTERNAL_CONNECTORS=FAKE_CONNECTORS,
    PREDICTNEED_SITE_URL="https://predictneed-ia.com",
)
class TikTokAdsAPITests(TestCase):

    def test_configuration_requires_v_version(self):
        self.assertEqual(
            _configuration_tiktok_ads()["api_version"],
            "v1.3",
        )

        with override_settings(
            PREDICTNEED_EXTERNAL_CONNECTORS={
                "tiktok_ads": {
                    **FAKE_CONNECTORS["tiktok_ads"],
                    "api_version": "1.3",
                }
            }
        ):
            with self.assertRaises(TikTokAdsConfigurationError):
                _configuration_tiktok_ads()

    def test_advertiser_id_is_numeric(self):
        self.assertEqual(normaliser_advertiser_id("12345"), "12345")
        with self.assertRaises(ValueError):
            normaliser_advertiser_id("adv-123")

    def test_authorization_url_uses_tiktok_parameters(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="tiktok-url",
            email="tiktok-url@example.com",
            password="MotDePasse-Solide-2026!",
        )
        client_pro = ClientProfessionnel.objects.create(
            utilisateur=user,
            nom_entreprise="TikTok URL",
            statut_abonnement="actif",
        )
        site = SiteClient.objects.create(
            client=client_pro,
            nom_site="TikTok URL Site",
            domaine="tiktok-url.example",
            actif=True,
            module_connecteurs_actif=True,
        )
        request = RequestFactory().get("/")
        request.user = user

        url = construire_url_autorisation(
            request,
            "tiktok_ads",
            site_id=site.id,
        )

        self.assertIn("app_id=app-id", url)
        self.assertIn("redirect_uri=", url)
        self.assertIn("scope=scope.a%2Cscope.b", url)
        self.assertNotIn("client_id=", url)
        self.assertNotIn("response_type=", url)

    @patch("predictor.tiktok_ads_api._request_json_tiktok")
    def test_token_exchange_posts_json_auth_code(self, request_json):
        request_json.return_value = {
            "access_token": "access-tiktok",
            "advertiser_ids": ["100", "200"],
            "scope": [4],
        }

        payload = echanger_code_contre_token_tiktok("auth-code")

        self.assertEqual(payload["access_token"], "access-tiktok")
        self.assertEqual(payload["advertiser_ids"], ["100", "200"])
        self.assertTrue(request_json.call_args.kwargs["token_url"])
        self.assertEqual(
            request_json.call_args.kwargs["payload"],
            {
                "app_id": "app-id",
                "secret": "secret",
                "auth_code": "auth-code",
            },
        )

    @patch("predictor.tiktok_ads_api._request_json_tiktok")
    def test_advertiser_discovery_normalizes_accounts(self, request_json):
        request_json.return_value = {
            "list": [
                {
                    "advertiser_id": "200",
                    "advertiser_name": "Advertiser B",
                    "currency": "usd",
                    "timezone": "Europe/Paris",
                    "advertiser_role": "ADMIN",
                },
                {
                    "advertiser_id": "100",
                    "advertiser_name": "Advertiser A",
                    "currency": "EUR",
                },
                {"advertiser_id": "200"},
            ]
        }

        comptes = lister_comptes_publicitaires_tiktok(
            "access-tiktok"
        )

        self.assertEqual(
            [compte["advertiser_id"] for compte in comptes],
            ["100", "200"],
        )
        self.assertEqual(comptes[1]["devise"], "USD")
        self.assertEqual(
            request_json.call_args.kwargs["params"]["app_id"],
            "app-id",
        )

    @patch("predictor.tiktok_ads_api._request_json_tiktok")
    def test_campaign_discovery_paginates(self, request_json):
        request_json.side_effect = [
            {
                "list": [
                    {
                        "campaign_id": "10",
                        "campaign_name": "Campagne 10",
                        "operation_status": "ENABLE",
                    }
                ],
                "page_info": {"total_page": 2},
            },
            {
                "list": [
                    {
                        "campaign_id": "20",
                        "campaign_name": "Campagne 20",
                        "operation_status": "DISABLE",
                    }
                ],
                "page_info": {"total_page": 2},
            },
        ]

        campagnes = lister_campagnes_tiktok(
            "access-tiktok",
            "123",
        )

        self.assertEqual(
            [campagne["campaign_id"] for campagne in campagnes],
            ["10", "20"],
        )
        self.assertEqual(request_json.call_count, 2)
        self.assertEqual(
            request_json.call_args_list[0].args[0],
            "/campaign/get/",
        )
        self.assertEqual(
            request_json.call_args_list[0].kwargs["params"]["fields"][0],
            "campaign_id",
        )

    @patch("predictor.tiktok_ads_api._request_json_tiktok")
    def test_reporting_query_requests_daily_campaign_metrics(self, request_json):
        request_json.return_value = {"list": []}

        lister_performances_campagnes_tiktok(
            "access-tiktok",
            "123",
            date_debut=date(2026, 8, 1),
            date_fin=date(2026, 8, 3),
        )

        self.assertEqual(
            request_json.call_args.args[0],
            "/report/integrated/get/",
        )
        params = request_json.call_args.kwargs["params"]
        self.assertEqual(params["report_type"], "BASIC")
        self.assertEqual(params["data_level"], "AUCTION_CAMPAIGN")
        self.assertIn("campaign_id", params["dimensions"])
        self.assertIn("stat_time_day", params["dimensions"])
        self.assertIn("spend", params["metrics"])
        self.assertIn("conversion", params["metrics"])


@override_settings(PREDICTNEED_EXTERNAL_CONNECTORS=FAKE_CONNECTORS)
class TikTokAdsTokenTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="tiktok-token",
            email="tiktok-token@example.com",
            password="MotDePasse-Solide-2026!",
        )
        self.client_pro = ClientProfessionnel.objects.create(
            utilisateur=self.user,
            nom_entreprise="TikTok Token",
            statut_abonnement="actif",
        )
        self.site = SiteClient.objects.create(
            client=self.client_pro,
            nom_site="TikTok Token Site",
            domaine="tiktok-token.example",
            actif=True,
            module_connecteurs_actif=True,
        )

    @patch("predictor.tiktok_ads_api.rafraichir_access_token_tiktok")
    def test_refresh_preserves_existing_refresh_token_when_omitted(self, refresh):
        refresh.return_value = {
            "access_token": "new-access",
            "expires_in": 86400,
        }
        old_refresh = signer_token("old-refresh")
        compte = CompteConnecteExterne.objects.create(
            client=self.client_pro,
            site=self.site,
            plateforme="tiktok_ads",
            identifiant_externe="123",
            nom_compte="Compte TikTok",
            access_token_signe=signer_token("old-access"),
            refresh_token_signe=old_refresh,
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        access_token = access_token_pour_compte_tiktok(compte)

        self.assertEqual(access_token, "new-access")
        compte.refresh_from_db()
        self.assertEqual(
            lire_token_signe(compte.access_token_signe),
            "new-access",
        )
        self.assertEqual(compte.refresh_token_signe, old_refresh)
