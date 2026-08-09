from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

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
        "variables_requises": [
            "GOOGLE_ADS_CLIENT_ID",
            "GOOGLE_ADS_CLIENT_SECRET",
            "GOOGLE_ADS_DEVELOPER_TOKEN",
        ],
        "variables_optionnelles": [
            "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
            "GOOGLE_ADS_API_VERSION",
        ],
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
class GoogleAdsSelectionTests(TestCase):

    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            username="google-selection",
            email="google-selection@example.com",
            password="MotDePasse-Solide-2026!",
        )
        self.client_pro = ClientProfessionnel.objects.create(
            utilisateur=self.user,
            nom_entreprise="Entreprise Google",
            statut_abonnement="actif",
        )
        self.site = SiteClient.objects.create(
            client=self.client_pro,
            nom_site="Site Google",
            domaine="google.example",
            actif=True,
            module_connecteurs_actif=True,
        )
        self.client.force_login(self.user)

    def _state(self):
        from django.core import signing

        return signing.dumps(
            {
                "plateforme": "google_ads",
                "user_id": self.user.id,
                "client_id": self.client_pro.id,
                "site_id": self.site.id,
            },
            salt="predictneed-connecteur-oauth",
        )

    def _accounts(self):
        return [
            {
                "customer_id": "1111111111",
                "nom": "Compte Google A",
                "devise": "EUR",
                "fuseau_horaire": "Europe/Paris",
                "manager": False,
                "test_account": False,
                "statut": "ENABLED",
                "login_customer_id": "",
            },
            {
                "customer_id": "2222222222",
                "nom": "Compte Google B",
                "devise": "USD",
                "fuseau_horaire": "America/New_York",
                "manager": False,
                "test_account": False,
                "statut": "ENABLED",
                "login_customer_id": "9999999999",
            },
        ]

    @patch("predictor.views.decouvrir_comptes_publicitaires")
    @patch(
        "predictor.views.echanger_code_contre_token",
        return_value={
            "access_token": "access-test",
            "refresh_token": "refresh-test",
            "token_type": "Bearer",
            "expires_in": 3600,
        },
    )
    def test_callback_requires_explicit_account_selection(
        self,
        exchange,
        discovery,
    ):
        discovery.return_value = self._accounts()

        response = self.client.get(
            reverse(
                "connecteur_oauth_callback",
                args=["google_ads"],
            ),
            {
                "code": "google-code",
                "state": self._state(),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("selectionner_compte_google_ads"),
            response["Location"],
        )
        self.assertFalse(
            CompteConnecteExterne.objects.filter(
                client=self.client_pro,
                site=self.site,
                plateforme="google_ads",
            ).exists()
        )

    @patch("predictor.views.decouvrir_comptes_publicitaires")
    @patch(
        "predictor.views.echanger_code_contre_token",
        return_value={
            "access_token": "access-test",
            "refresh_token": "refresh-test",
            "token_type": "Bearer",
            "expires_in": 3600,
        },
    )
    def test_user_can_choose_second_account_not_first(
        self,
        exchange,
        discovery,
    ):
        discovery.return_value = self._accounts()

        callback = self.client.get(
            reverse(
                "connecteur_oauth_callback",
                args=["google_ads"],
            ),
            {
                "code": "google-code",
                "state": self._state(),
            },
        )

        flow_id = callback["Location"].split("flow=", 1)[1]

        response = self.client.post(
            reverse("selectionner_compte_google_ads"),
            {
                "flow": flow_id,
                "customer_id": "2222222222",
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('module_connecteurs')}?site={self.site.id}",
        )

        account = CompteConnecteExterne.objects.get(
            client=self.client_pro,
            site=self.site,
            plateforme="google_ads",
        )

        self.assertEqual(
            account.identifiant_externe,
            "2222222222",
        )
        self.assertEqual(
            account.configuration["login_customer_id"],
            "9999999999",
        )
        self.assertFalse(
            CompteConnecteExterne.objects.filter(
                client=self.client_pro,
                site=self.site,
                plateforme="google_ads",
                identifiant_externe="1111111111",
            ).exists()
        )

    @patch("predictor.views.decouvrir_comptes_publicitaires")
    @patch(
        "predictor.views.echanger_code_contre_token",
        return_value={
            "access_token": "access-test",
            "refresh_token": "refresh-test",
            "token_type": "Bearer",
            "expires_in": 3600,
        },
    )
    def test_unknown_customer_id_is_rejected(
        self,
        exchange,
        discovery,
    ):
        discovery.return_value = self._accounts()

        callback = self.client.get(
            reverse(
                "connecteur_oauth_callback",
                args=["google_ads"],
            ),
            {
                "code": "google-code",
                "state": self._state(),
            },
        )

        flow_id = callback["Location"].split("flow=", 1)[1]

        response = self.client.post(
            reverse("selectionner_compte_google_ads"),
            {
                "flow": flow_id,
                "customer_id": "9999999999",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            CompteConnecteExterne.objects.filter(
                client=self.client_pro,
                site=self.site,
                plateforme="google_ads",
            ).exists()
        )

    def test_selection_without_pending_flow_is_rejected(self):
        response = self.client.get(
            reverse("selectionner_compte_google_ads"),
            {"flow": "inconnu"},
        )

        self.assertRedirects(
            response,
            f"{reverse('module_connecteurs')}?site={self.site.id}",
        )

    @override_settings(
        PREDICTNEED_EXTERNAL_CONNECTORS={
            "google_ads": {
                "nom": "Google Ads",
                "description": "Test",
                "client_id": "client",
                "client_secret": "secret",
                "developer_token": "",
                "auth_url": "https://accounts.test/auth",
                "token_url": "https://accounts.test/token",
                "scopes": [],
            }
        }
    )
    def test_connect_button_requires_developer_token(self):
        response = self.client.get(
            reverse("module_connecteurs"),
            {"site": self.site.id},
        )

        self.assertNotContains(
            response,
            reverse(
                "demarrer_oauth_connecteur",
                args=["google_ads"],
            ),
        )
