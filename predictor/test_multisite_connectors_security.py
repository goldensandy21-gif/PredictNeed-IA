from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import signing
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

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
        "scopes": ["ads.read"],
        "variables_requises": [
            "GOOGLE_ADS_CLIENT_ID",
            "GOOGLE_ADS_CLIENT_SECRET",
        ],
        "variables_optionnelles": [],
    }
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
class MultisiteConnectorSecurityTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            username="connect-owner",
            email="connect-owner@example.com",
            password="MotDePasse-Solide-2026!",
        )
        self.client_pro = ClientProfessionnel.objects.create(
            utilisateur=self.user,
            nom_entreprise="Entreprise Connecteurs",
            statut_abonnement="actif",
        )
        self.site_a = SiteClient.objects.create(
            client=self.client_pro,
            nom_site="Site A",
            domaine="a.example",
            actif=True,
            module_connecteurs_actif=True,
        )
        self.site_b = SiteClient.objects.create(
            client=self.client_pro,
            nom_site="Site B",
            domaine="b.example",
            actif=True,
            module_connecteurs_actif=True,
        )

        self.other_user = User.objects.create_user(
            username="other-owner",
            email="other-owner@example.com",
            password="MotDePasse-Solide-2026!",
        )
        self.other_client = ClientProfessionnel.objects.create(
            utilisateur=self.other_user,
            nom_entreprise="Autre Entreprise",
            statut_abonnement="actif",
        )
        self.other_site = SiteClient.objects.create(
            client=self.other_client,
            nom_site="Site Etranger",
            domaine="other.example",
            actif=True,
            module_connecteurs_actif=True,
        )

        self.client.force_login(self.user)

    def _state(self, *, client_id=None, site_id=None):
        return signing.dumps(
            {
                "plateforme": "google_ads",
                "user_id": self.user.id,
                "client_id": (
                    self.client_pro.id
                    if client_id is None
                    else client_id
                ),
                "site_id": self.site_a.id if site_id is None else site_id,
            },
            salt="predictneed-connecteur-oauth",
        )

    def test_client_sees_simple_oauth_connect_button_without_internal_secrets(self):
        response = self.client.get(
            reverse("module_connecteurs"),
            {"site": self.site_a.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Google Ads")
        self.assertContains(response, "Connecter")
        self.assertContains(response, "plateforme officielle")
        self.assertContains(response, "Il ne donne jamais son mot de passe")
        self.assertContains(
            response,
            f"{reverse('demarrer_oauth_connecteur', args=['google_ads'])}?site={self.site_a.id}",
        )
        self.assertNotContains(response, "Configuration interne administrateur")
        self.assertNotContains(response, "GOOGLE_ADS_CLIENT_ID")
        self.assertNotContains(response, "GOOGLE_ADS_CLIENT_SECRET")

    def test_oauth_start_requires_a_site(self):
        response = self.client.get(
            reverse("demarrer_oauth_connecteur", args=["google_ads"])
        )
        self.assertRedirects(response, reverse("module_connecteurs"))

    def test_oauth_start_rejects_another_clients_site(self):
        response = self.client.get(
            reverse("demarrer_oauth_connecteur", args=["google_ads"]),
            {"site": self.other_site.id},
        )
        self.assertRedirects(response, reverse("module_connecteurs"))

    @patch("predictor.views.echanger_code_contre_token")
    def test_oauth_callback_rejects_another_client_state_before_token_exchange(
        self,
        exchange,
    ):
        response = self.client.get(
            reverse("connecteur_oauth_callback", args=["google_ads"]),
            {
                "code": "fake-code",
                "state": self._state(client_id=self.other_client.id),
            },
        )
        self.assertRedirects(response, reverse("module_connecteurs"))
        exchange.assert_not_called()

    @patch("predictor.views.echanger_code_contre_token")
    def test_oauth_callback_rejects_foreign_site_before_token_exchange(
        self,
        exchange,
    ):
        response = self.client.get(
            reverse("connecteur_oauth_callback", args=["google_ads"]),
            {
                "code": "fake-code",
                "state": self._state(site_id=self.other_site.id),
            },
        )
        self.assertRedirects(response, reverse("module_connecteurs"))
        exchange.assert_not_called()

    @patch(
        "predictor.views.decouvrir_comptes_publicitaires",
        return_value=[
            {
                "customer_id": "1234567890",
                "nom": "Compte partagé",
                "devise": "EUR",
                "fuseau_horaire": "Europe/Paris",
                "manager": False,
                "test_account": False,
                "statut": "ENABLED",
                "login_customer_id": "",
            }
        ],
    )
    @patch(
        "predictor.views.echanger_code_contre_token",
        return_value={
            "access_token": "token-test",
            "refresh_token": "refresh-test",
            "token_type": "Bearer",
            "expires_in": 3600,
        },
    )
    def test_same_external_account_is_kept_separate_for_two_sites(
        self,
        exchange,
        discovery,
    ):
        for site in (self.site_a, self.site_b):
            response = self.client.get(
                reverse("connecteur_oauth_callback", args=["google_ads"]),
                {
                    "code": f"code-{site.id}",
                    "state": self._state(site_id=site.id),
                },
            )

            self.assertEqual(response.status_code, 302)
            self.assertIn(
                reverse("selectionner_compte_google_ads"),
                response["Location"],
            )

            flow_id = response["Location"].split("flow=", 1)[1]

            selection = self.client.post(
                reverse("selectionner_compte_google_ads"),
                {
                    "flow": flow_id,
                    "customer_id": "1234567890",
                },
            )

            self.assertRedirects(
                selection,
                f"{reverse('module_connecteurs')}?site={site.id}",
            )

        accounts = CompteConnecteExterne.objects.filter(
            client=self.client_pro,
            plateforme="google_ads",
            identifiant_externe="1234567890",
        )
        self.assertEqual(accounts.count(), 2)
        self.assertSetEqual(
            set(accounts.values_list("site_id", flat=True)),
            {self.site_a.id, self.site_b.id},
        )
        self.assertEqual(exchange.call_count, 2)
        self.assertEqual(discovery.call_count, 2)

    def test_database_rejects_duplicate_external_account_on_same_site(self):
        fields = {
            "client": self.client_pro,
            "site": self.site_a,
            "plateforme": "google_ads",
            "identifiant_externe": "duplicate-account",
            "nom_compte": "Compte test",
        }
        CompteConnecteExterne.objects.create(**fields)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CompteConnecteExterne.objects.create(**fields)

    def test_sync_rejects_legacy_site_less_connector(self):
        account = CompteConnecteExterne.objects.create(
            client=self.client_pro,
            site=None,
            plateforme="google_ads",
            identifiant_externe="legacy-account",
            nom_compte="Ancien compte",
        )
        response = self.client.post(
            reverse("synchroniser_compte_connecteur", args=[account.id])
        )
        self.assertEqual(response.status_code, 404)

    @patch(
        "predictor.views.synchroniser_compte_depuis_utm",
        return_value=0,
    )
    def test_sync_is_limited_to_connector_site(self, sync):
        account = CompteConnecteExterne.objects.create(
            client=self.client_pro,
            site=self.site_b,
            plateforme="google_ads",
            identifiant_externe="site-b-account",
            nom_compte="Compte B",
        )
        response = self.client.post(
            reverse("synchroniser_compte_connecteur", args=[account.id])
        )
        self.assertRedirects(
            response,
            f"{reverse('module_connecteurs')}?site={self.site_b.id}",
        )

        self.assertEqual(sync.call_count, 1)
        sites_arg = sync.call_args.args[1]
        self.assertListEqual(
            list(sites_arg.values_list("id", flat=True)),
            [self.site_b.id],
        )

    def test_disconnect_rejects_another_clients_account(self):
        account = CompteConnecteExterne.objects.create(
            client=self.other_client,
            site=self.other_site,
            plateforme="google_ads",
            identifiant_externe="foreign-account",
            nom_compte="Compte étranger",
        )
        response = self.client.post(
            reverse("deconnecter_compte_connecteur", args=[account.id])
        )
        self.assertEqual(response.status_code, 404)

    def test_retargeting_rejects_another_clients_site(self):
        response = self.client.post(
            reverse(
                "mettre_a_jour_retargeting_site",
                args=[self.other_site.id],
            ),
            {
                "retargeting_actif": "on",
                "meta_pixel_id": "123456",
            },
        )
        self.assertEqual(response.status_code, 404)
        self.other_site.refresh_from_db()
        self.assertFalse(self.other_site.retargeting_actif)
