from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from .external_connectors import lire_token_signe, signer_token
from .linkedin_ads_api import (
    LinkedInAdsConfigurationError,
    _configuration_linkedin_ads,
    access_token_pour_compte_linkedin,
    lister_campagnes_linkedin,
    lister_comptes_publicitaires_linkedin,
    lister_performances_campagnes_linkedin,
    normaliser_sponsored_account_id,
)
from .models import (
    ClientProfessionnel,
    CompteConnecteExterne,
    SiteClient,
)


FAKE_CONNECTORS = {
    "linkedin_ads": {
        "nom": "LinkedIn Ads",
        "description": "Test LinkedIn Ads",
        "client_id": "linkedin-client",
        "client_secret": "linkedin-secret",
        "api_version": "202606",
        "auth_url": "https://www.linkedin.com/oauth/v2/authorization",
        "token_url": "https://www.linkedin.com/oauth/v2/accessToken",
        "scopes": ["r_ads", "r_ads_reporting"],
    },
}


@override_settings(PREDICTNEED_EXTERNAL_CONNECTORS=FAKE_CONNECTORS)
class LinkedInAdsAPITests(TestCase):

    def test_configuration_requires_yyyy_mm_without_dash(self):
        self.assertEqual(
            _configuration_linkedin_ads()["api_version"],
            "202606",
        )

        with override_settings(
            PREDICTNEED_EXTERNAL_CONNECTORS={
                "linkedin_ads": {
                    **FAKE_CONNECTORS["linkedin_ads"],
                    "api_version": "2026-06",
                }
            }
        ):
            with self.assertRaises(LinkedInAdsConfigurationError):
                _configuration_linkedin_ads()

    def test_account_id_accepts_sponsored_account_urn(self):
        self.assertEqual(
            normaliser_sponsored_account_id(
                "urn:li:sponsoredAccount:123456"
            ),
            "123456",
        )

    @patch("predictor.linkedin_ads_api._request_json")
    def test_account_discovery_paginates_and_normalizes(self, request_json):
        request_json.side_effect = [
            {
                "elements": [
                    {
                        "id": 100,
                        "name": "Compte B",
                        "currency": "usd",
                        "status": "ACTIVE",
                        "type": "BUSINESS",
                        "test": False,
                        "servingStatuses": ["RUNNABLE"],
                    },
                ],
                "metadata": {"nextPageToken": "suite"},
            },
            {
                "elements": [
                    {
                        "id": "50",
                        "name": "Compte A",
                        "currency": "EUR",
                        "status": "ACTIVE",
                    },
                    {
                        "id": "100",
                        "name": "Doublon",
                    },
                ],
            },
        ]

        comptes = lister_comptes_publicitaires_linkedin(
            "access-token"
        )

        self.assertEqual(
            [compte["account_id"] for compte in comptes],
            ["50", "100"],
        )
        self.assertEqual(comptes[1]["devise"], "USD")
        self.assertEqual(
            comptes[1]["urn"],
            "urn:li:sponsoredAccount:100",
        )
        self.assertEqual(request_json.call_count, 2)
        self.assertEqual(
            request_json.call_args_list[1].kwargs["params"]["pageToken"],
            "suite",
        )

    @patch("predictor.linkedin_ads_api._request_json")
    def test_campaign_discovery_uses_restli_search(self, request_json):
        request_json.return_value = {
            "elements": [
                {
                    "id": 900,
                    "name": "Campagne LinkedIn",
                    "status": "ACTIVE",
                    "account": "urn:li:sponsoredAccount:100",
                },
            ],
        }

        campagnes = lister_campagnes_linkedin(
            "access-token",
            "urn:li:sponsoredAccount:100",
        )

        self.assertEqual(campagnes[0]["campaign_id"], "900")
        self.assertEqual(
            request_json.call_args.args[0],
            "/adAccounts/100/adCampaigns",
        )
        params = request_json.call_args.kwargs["params"]
        self.assertEqual(params["q"], "search")
        self.assertIn("ACTIVE", params["search"])

    @patch("predictor.linkedin_ads_api._request_json")
    def test_analytics_query_requests_daily_campaign_metrics(self, request_json):
        request_json.return_value = {"elements": []}

        lister_performances_campagnes_linkedin(
            "access-token",
            "123",
            date_debut=date(2026, 8, 1),
            date_fin=date(2026, 8, 3),
        )

        self.assertEqual(
            request_json.call_args.args[0],
            "/adAnalytics",
        )
        params = request_json.call_args.kwargs["params"]
        self.assertEqual(params["q"], "analytics")
        self.assertEqual(params["pivot"], "CAMPAIGN")
        self.assertEqual(params["timeGranularity"], "DAILY")
        self.assertEqual(
            params["accounts"],
            "List(urn:li:sponsoredAccount:123)",
        )
        self.assertIn("costInLocalCurrency", params["fields"])
        self.assertIn("externalWebsiteConversions", params["fields"])


@override_settings(PREDICTNEED_EXTERNAL_CONNECTORS=FAKE_CONNECTORS)
class LinkedInAdsTokenTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="linkedin-token",
            email="linkedin-token@example.com",
            password="MotDePasse-Solide-2026!",
        )
        self.client_pro = ClientProfessionnel.objects.create(
            utilisateur=self.user,
            nom_entreprise="LinkedIn Token",
            statut_abonnement="actif",
        )
        self.site = SiteClient.objects.create(
            client=self.client_pro,
            nom_site="LinkedIn Token Site",
            domaine="linkedin-token.example",
            actif=True,
            module_connecteurs_actif=True,
        )

    @patch("predictor.linkedin_ads_api.rafraichir_access_token_linkedin")
    def test_refresh_preserves_existing_refresh_token_when_omitted(self, refresh):
        refresh.return_value = {
            "access_token": "new-access",
            "expires_in": 3600,
        }
        old_refresh = signer_token("old-refresh")
        compte = CompteConnecteExterne.objects.create(
            client=self.client_pro,
            site=self.site,
            plateforme="linkedin_ads",
            identifiant_externe="123",
            nom_compte="Compte LinkedIn",
            access_token_signe=signer_token("old-access"),
            refresh_token_signe=old_refresh,
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        access_token = access_token_pour_compte_linkedin(compte)

        self.assertEqual(access_token, "new-access")
        compte.refresh_from_db()
        self.assertEqual(
            lire_token_signe(compte.access_token_signe),
            "new-access",
        )
        self.assertEqual(compte.refresh_token_signe, old_refresh)
