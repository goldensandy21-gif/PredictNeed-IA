from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from .meta_ads_api import (
    MetaAdsAPIError,
    MetaAdsConfigurationError,
    _configuration_meta_ads,
    _extraire_conversions_meta,
    _normaliser_compte_meta,
    lister_comptes_publicitaires_meta,
    lister_performances_campagnes_meta,
    normaliser_account_id_meta,
)


BASE_CONNECTORS = {
    "meta_ads": {
        "api_version": "v25.0",
    },
}


@override_settings(
    PREDICTNEED_EXTERNAL_CONNECTORS=BASE_CONNECTORS
)
class MetaAdsAPITests(SimpleTestCase):

    def test_configuration_accepts_version_25(self):
        configuration = _configuration_meta_ads()

        self.assertEqual(
            configuration["api_version"],
            "v25.0",
        )
        self.assertEqual(
            configuration["base_url"],
            "https://graph.facebook.com/v25.0",
        )

    @override_settings(
        PREDICTNEED_EXTERNAL_CONNECTORS={
            "meta_ads": {
                "api_version": "25",
            },
        }
    )
    def test_invalid_api_version_is_rejected(self):
        with self.assertRaises(
            MetaAdsConfigurationError
        ):
            _configuration_meta_ads()

    def test_account_normalization_uses_graph_id(self):
        compte = _normaliser_compte_meta({
            "id": "act_123456",
            "name": "Compte Meta",
            "currency": "eur",
            "timezone_name": "Europe/Paris",
            "account_status": 1,
        })

        self.assertEqual(
            compte["account_id"],
            "123456",
        )
        self.assertEqual(
            compte["graph_id"],
            "act_123456",
        )
        self.assertEqual(
            compte["devise"],
            "EUR",
        )
        self.assertEqual(
            compte["fuseau_horaire"],
            "Europe/Paris",
        )
        self.assertEqual(
            compte["statut_meta"],
            1,
        )

    def test_account_without_identifier_is_ignored(self):
        self.assertIsNone(
            _normaliser_compte_meta({
                "name": "Sans identifiant",
            })
        )

    def test_meta_account_id_is_normalized(self):
        self.assertEqual(
            normaliser_account_id_meta("act_123456"),
            "123456",
        )

    def test_invalid_meta_account_id_is_rejected(self):
        with self.assertRaises(ValueError):
            normaliser_account_id_meta("act_abc")

    def test_conversions_use_conversions_field_when_available(self):
        total = _extraire_conversions_meta({
            "conversions": [
                {"action_type": "lead", "value": "2.5"},
                {"action_type": "purchase", "value": "1"},
            ],
            "actions": [
                {"action_type": "link_click", "value": "99"},
            ],
        })

        self.assertEqual(str(total), "3.5")

    def test_conversion_actions_are_filtered(self):
        total = _extraire_conversions_meta({
            "actions": [
                {"action_type": "link_click", "value": "99"},
                {"action_type": "lead", "value": "3"},
                {
                    "action_type": "offsite_conversion.fb_pixel_purchase",
                    "value": "2",
                },
            ],
        })

        self.assertEqual(str(total), "5")

    @patch("predictor.meta_ads_api._requete_graph")
    def test_account_discovery_paginates(
        self,
        graph_request,
    ):
        graph_request.side_effect = [
            {
                "data": [
                    {
                        "id": "act_100",
                        "account_id": "100",
                        "name": "Compte A",
                        "currency": "EUR",
                        "timezone_name": "Europe/Paris",
                        "account_status": 1,
                    },
                ],
                "paging": {
                    "cursors": {
                        "after": "CURSOR-1",
                    },
                    "next": "https://graph.facebook.com/next",
                },
            },
            {
                "data": [
                    {
                        "id": "act_200",
                        "account_id": "200",
                        "name": "Compte B",
                        "currency": "USD",
                        "timezone_name": "America/New_York",
                        "account_status": 1,
                    },
                ],
            },
        ]

        comptes = lister_comptes_publicitaires_meta(
            "token-test"
        )

        self.assertEqual(
            [item["account_id"] for item in comptes],
            ["100", "200"],
        )
        self.assertEqual(
            graph_request.call_count,
            2,
        )

        second_params = graph_request.call_args_list[
            1
        ].kwargs["params"]
        self.assertEqual(
            second_params["after"],
            "CURSOR-1",
        )

    @patch("predictor.meta_ads_api._requete_graph")
    def test_duplicate_accounts_are_removed(
        self,
        graph_request,
    ):
        graph_request.return_value = {
            "data": [
                {
                    "id": "act_100",
                    "account_id": "100",
                    "name": "A",
                },
                {
                    "id": "act_100",
                    "account_id": "100",
                    "name": "A duplicate",
                },
            ],
        }

        comptes = lister_comptes_publicitaires_meta(
            "token-test"
        )

        self.assertEqual(len(comptes), 1)
        self.assertEqual(
            comptes[0]["account_id"],
            "100",
        )

    @patch("predictor.meta_ads_api._requete_graph")
    def test_invalid_data_payload_is_rejected(
        self,
        graph_request,
    ):
        graph_request.return_value = {
            "data": {
                "unexpected": True,
            },
        }

        with self.assertRaises(MetaAdsAPIError):
            lister_comptes_publicitaires_meta(
                "token-test"
            )

    @patch("predictor.meta_ads_api._requete_graph")
    def test_campaign_insights_use_daily_campaign_level(
        self,
        graph_request,
    ):
        graph_request.return_value = {
            "data": [
                {
                    "campaign_id": "100",
                    "campaign_name": "Campagne Meta",
                    "date_start": "2026-08-08",
                    "impressions": "1000",
                }
            ]
        }

        rows = lister_performances_campagnes_meta(
            "token-test",
            "act_123456",
            periode="LAST_30_DAYS",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            graph_request.call_args.args[0],
            "/act_123456/insights",
        )
        params = graph_request.call_args.kwargs["params"]
        self.assertEqual(params["level"], "campaign")
        self.assertEqual(params["date_preset"], "last_30d")
        self.assertEqual(params["time_increment"], 1)
        self.assertIn("campaign_id", params["fields"])
        self.assertIn("spend", params["fields"])
        self.assertIn("actions", params["fields"])

    @patch("predictor.meta_ads_api._requete_graph")
    def test_campaign_insights_paginate(
        self,
        graph_request,
    ):
        graph_request.side_effect = [
            {
                "data": [{"campaign_id": "100"}],
                "paging": {
                    "cursors": {"after": "CURSOR-1"},
                    "next": "https://graph.facebook.com/next",
                },
            },
            {"data": [{"campaign_id": "200"}]},
        ]

        rows = lister_performances_campagnes_meta(
            "token-test",
            "123456",
        )

        self.assertEqual(
            [row["campaign_id"] for row in rows],
            ["100", "200"],
        )
        self.assertEqual(
            graph_request.call_args_list[1].kwargs["params"]["after"],
            "CURSOR-1",
        )
