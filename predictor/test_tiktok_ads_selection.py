from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import signing
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .external_connectors import signer_token
from .models import (
    ClientProfessionnel,
    CompteConnecteExterne,
    SiteClient,
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
        "scopes": [],
    },
}

TEST_STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


@override_settings(
    PREDICTNEED_EXTERNAL_CONNECTORS=FAKE_CONNECTORS,
    PREDICTNEED_SITE_URL="https://predictneed-ia.com",
    STORAGES=TEST_STORAGES,
)
class TikTokAdsSelectionTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="tiktok-selection",
            email="tiktok-selection@example.com",
            password="MotDePasse-Solide-2026!",
        )
        self.client_pro = ClientProfessionnel.objects.create(
            utilisateur=self.user,
            nom_entreprise="Entreprise TikTok",
            statut_abonnement="actif",
        )
        self.site = SiteClient.objects.create(
            client=self.client_pro,
            nom_site="Site TikTok",
            domaine="tiktok.example",
            actif=True,
            module_connecteurs_actif=True,
        )
        self.accounts = [
            {
                "advertiser_id": "100",
                "nom": "Advertiser TikTok A",
                "devise": "EUR",
                "fuseau_horaire": "Europe/Paris",
                "statut": "STATUS_ENABLE",
                "role": "ADMIN",
            },
            {
                "advertiser_id": "200",
                "nom": "Advertiser TikTok B",
                "devise": "USD",
                "fuseau_horaire": "America/New_York",
                "statut": "STATUS_ENABLE",
                "role": "ANALYST",
            },
        ]
        self.client.force_login(self.user)

    def _state(self):
        return signing.dumps(
            {
                "plateforme": "tiktok_ads",
                "user_id": self.user.id,
                "client_id": self.client_pro.id,
                "site_id": self.site.id,
            },
            salt="predictneed-connecteur-oauth",
        )

    def _seed_flow(self, *, flow_id="flow-tiktok"):
        session = self.client.session
        session["tiktok_ads_oauth_flows"] = {
            flow_id: {
                "user_id": self.user.id,
                "client_id": self.client_pro.id,
                "site_id": self.site.id,
                "created_at": timezone.now().timestamp(),
                "access_token_signe": signer_token(
                    "access-tiktok"
                ),
                "refresh_token_signe": signer_token(
                    "refresh-tiktok"
                ),
                "token_type": "Bearer",
                "expires_in": 86400,
                "comptes": self.accounts,
            }
        }
        session.save()
        return flow_id

    @patch("predictor.views.echanger_code_contre_token")
    @patch("predictor.views.lister_comptes_publicitaires_tiktok")
    @patch(
        "predictor.views.echanger_code_contre_token_tiktok",
        return_value={
            "access_token": "access-tiktok",
            "refresh_token": "refresh-tiktok",
            "token_type": "Bearer",
            "expires_in": 86400,
            "advertiser_ids": ["100", "200"],
        },
    )
    def test_callback_uses_auth_code_and_requires_explicit_selection(
        self,
        exchange_tiktok,
        discovery,
        exchange_generic,
    ):
        discovery.return_value = self.accounts

        response = self.client.get(
            reverse(
                "connecteur_oauth_callback",
                args=["tiktok_ads"],
            ),
            {
                "auth_code": "auth-code-tiktok",
                "state": self._state(),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("selectionner_compte_tiktok_ads"),
            response["Location"],
        )
        self.assertEqual(exchange_tiktok.call_count, 1)
        self.assertEqual(exchange_generic.call_count, 0)
        discovery.assert_called_once_with(
            "access-tiktok",
            advertiser_ids=["100", "200"],
        )
        self.assertFalse(
            CompteConnecteExterne.objects.filter(
                client=self.client_pro,
                site=self.site,
                plateforme="tiktok_ads",
            ).exists()
        )

    def test_selection_page_displays_discovered_advertisers(self):
        flow_id = self._seed_flow()

        response = self.client.get(
            reverse("selectionner_compte_tiktok_ads"),
            {"flow": flow_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Advertiser TikTok A")
        self.assertContains(response, "Advertiser TikTok B")

    def test_explicit_selection_creates_only_chosen_advertiser(self):
        flow_id = self._seed_flow()

        response = self.client.post(
            reverse("selectionner_compte_tiktok_ads"),
            {
                "flow": flow_id,
                "advertiser_id": "200",
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('module_connecteurs')}?site={self.site.id}",
        )

        comptes = CompteConnecteExterne.objects.filter(
            plateforme="tiktok_ads"
        )
        self.assertEqual(comptes.count(), 1)
        compte = comptes.get()
        self.assertEqual(compte.identifiant_externe, "200")
        self.assertEqual(compte.nom_compte, "Advertiser TikTok B")
        self.assertEqual(
            compte.configuration["advertiser_id"],
            "200",
        )
        self.assertEqual(compte.configuration["devise"], "USD")
        self.assertEqual(
            self.client.session.get(
                "tiktok_ads_oauth_flows",
                {},
            ),
            {},
        )

    def test_unknown_advertiser_id_is_refused(self):
        flow_id = self._seed_flow()

        response = self.client.post(
            reverse("selectionner_compte_tiktok_ads"),
            {
                "flow": flow_id,
                "advertiser_id": "999",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Sélection TikTok Ads invalide",
        )
        self.assertFalse(
            CompteConnecteExterne.objects.filter(
                plateforme="tiktok_ads"
            ).exists()
        )
