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
class LinkedInAdsSelectionTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="linkedin-selection",
            email="linkedin-selection@example.com",
            password="MotDePasse-Solide-2026!",
        )
        self.client_pro = ClientProfessionnel.objects.create(
            utilisateur=self.user,
            nom_entreprise="Entreprise LinkedIn",
            statut_abonnement="actif",
        )
        self.site = SiteClient.objects.create(
            client=self.client_pro,
            nom_site="Site LinkedIn",
            domaine="linkedin.example",
            actif=True,
            module_connecteurs_actif=True,
        )
        self.accounts = [
            {
                "account_id": "100",
                "urn": "urn:li:sponsoredAccount:100",
                "nom": "Compte LinkedIn A",
                "devise": "EUR",
                "statut": "ACTIVE",
                "type": "BUSINESS",
                "test_account": False,
                "serving_statuses": ["RUNNABLE"],
            },
            {
                "account_id": "200",
                "urn": "urn:li:sponsoredAccount:200",
                "nom": "Compte LinkedIn B",
                "devise": "USD",
                "statut": "ACTIVE",
                "type": "BUSINESS",
                "test_account": False,
                "serving_statuses": ["RUNNABLE"],
            },
        ]
        self.client.force_login(self.user)

    def _state(self):
        return signing.dumps(
            {
                "plateforme": "linkedin_ads",
                "user_id": self.user.id,
                "client_id": self.client_pro.id,
                "site_id": self.site.id,
            },
            salt="predictneed-connecteur-oauth",
        )

    def _seed_flow(self, *, flow_id="flow-linkedin"):
        session = self.client.session
        session["linkedin_ads_oauth_flows"] = {
            flow_id: {
                "user_id": self.user.id,
                "client_id": self.client_pro.id,
                "site_id": self.site.id,
                "created_at": timezone.now().timestamp(),
                "access_token_signe": signer_token(
                    "access-linkedin"
                ),
                "refresh_token_signe": signer_token(
                    "refresh-linkedin"
                ),
                "token_type": "Bearer",
                "expires_in": 3600,
                "comptes": self.accounts,
            }
        }
        session.save()
        return flow_id

    @patch("predictor.views.lister_comptes_publicitaires_linkedin")
    @patch(
        "predictor.views.echanger_code_contre_token",
        return_value={
            "access_token": "access-linkedin",
            "refresh_token": "refresh-linkedin",
            "token_type": "Bearer",
            "expires_in": 3600,
        },
    )
    def test_callback_discovers_accounts_without_auto_selecting(
        self,
        exchange,
        discovery,
    ):
        discovery.return_value = self.accounts

        response = self.client.get(
            reverse(
                "connecteur_oauth_callback",
                args=["linkedin_ads"],
            ),
            {
                "code": "linkedin-code",
                "state": self._state(),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("selectionner_compte_linkedin_ads"),
            response["Location"],
        )
        self.assertFalse(
            CompteConnecteExterne.objects.filter(
                client=self.client_pro,
                site=self.site,
                plateforme="linkedin_ads",
            ).exists()
        )
        flows = self.client.session.get(
            "linkedin_ads_oauth_flows",
            {},
        )
        self.assertEqual(len(flows), 1)
        pending = next(iter(flows.values()))
        self.assertEqual(
            [item["account_id"] for item in pending["comptes"]],
            ["100", "200"],
        )

    def test_selection_page_displays_discovered_accounts(self):
        flow_id = self._seed_flow()

        response = self.client.get(
            reverse("selectionner_compte_linkedin_ads"),
            {"flow": flow_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Compte LinkedIn A")
        self.assertContains(response, "Compte LinkedIn B")
        self.assertEqual(
            CompteConnecteExterne.objects.filter(
                plateforme="linkedin_ads"
            ).count(),
            0,
        )

    def test_explicit_selection_creates_only_chosen_account(self):
        flow_id = self._seed_flow()

        response = self.client.post(
            reverse("selectionner_compte_linkedin_ads"),
            {
                "flow": flow_id,
                "account_id": "200",
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('module_connecteurs')}?site={self.site.id}",
        )

        comptes = CompteConnecteExterne.objects.filter(
            plateforme="linkedin_ads"
        )
        self.assertEqual(comptes.count(), 1)
        compte = comptes.get()
        self.assertEqual(compte.identifiant_externe, "200")
        self.assertEqual(compte.nom_compte, "Compte LinkedIn B")
        self.assertEqual(
            compte.configuration["urn"],
            "urn:li:sponsoredAccount:200",
        )
        self.assertEqual(compte.configuration["devise"], "USD")
        self.assertEqual(
            self.client.session.get(
                "linkedin_ads_oauth_flows",
                {},
            ),
            {},
        )

    def test_unknown_account_id_is_refused(self):
        flow_id = self._seed_flow()

        response = self.client.post(
            reverse("selectionner_compte_linkedin_ads"),
            {
                "flow": flow_id,
                "account_id": "999",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Sélection LinkedIn Ads invalide",
        )
        self.assertFalse(
            CompteConnecteExterne.objects.filter(
                plateforme="linkedin_ads"
            ).exists()
        )
