from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .external_connectors import signer_token
from .models import (
    ClientProfessionnel,
    CompteConnecteExterne,
    SiteClient,
)


TEST_STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


@override_settings(STORAGES=TEST_STORAGES)
class MetaAdsAccountSelectionTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="meta-owner",
            email="meta-owner@example.com",
            password="MotDePasse-Solide-2026!",
        )
        self.pro = ClientProfessionnel.objects.create(
            utilisateur=self.user,
            nom_entreprise="Meta Corp",
            statut_abonnement="actif",
        )
        self.site = SiteClient.objects.create(
            client=self.pro,
            nom_site="Meta Site",
            domaine="meta.example",
            actif=True,
            module_connecteurs_actif=True,
        )
        self.accounts = [
            {
                "account_id": "100",
                "graph_id": "act_100",
                "nom": "Compte Meta A",
                "devise": "EUR",
                "fuseau_horaire": "Europe/Paris",
                "statut_meta": 1,
            },
            {
                "account_id": "200",
                "graph_id": "act_200",
                "nom": "Compte Meta B",
                "devise": "USD",
                "fuseau_horaire": "America/New_York",
                "statut_meta": 1,
            },
        ]
        self.client.force_login(self.user)

    def _seed_flow(
        self,
        *,
        flow_id="flow-meta",
        accounts=None,
        created_at=None,
        user_id=None,
        client_id=None,
        site_id=None,
        refresh_token="refresh-meta",
    ):
        session = self.client.session
        session["meta_ads_oauth_flows"] = {
            flow_id: {
                "user_id": (
                    self.user.id
                    if user_id is None
                    else user_id
                ),
                "client_id": (
                    self.pro.id
                    if client_id is None
                    else client_id
                ),
                "site_id": (
                    self.site.id
                    if site_id is None
                    else site_id
                ),
                "created_at": (
                    timezone.now().timestamp()
                    if created_at is None
                    else created_at
                ),
                "access_token_signe": signer_token(
                    "access-meta"
                ),
                "refresh_token_signe": (
                    signer_token(refresh_token)
                    if refresh_token
                    else ""
                ),
                "token_type": "Bearer",
                "expires_in": 3600,
                "comptes": (
                    self.accounts
                    if accounts is None
                    else accounts
                ),
            }
        }
        session.save()
        return flow_id

    def test_callback_discovers_accounts_without_auto_selecting(self):
        state_payload = {
            "user_id": self.user.id,
            "plateforme": "meta_ads",
            "client_id": self.pro.id,
            "site_id": self.site.id,
        }

        with patch(
            "predictor.views.verifier_state_connecteur",
            return_value=state_payload,
        ), patch(
            "predictor.views.echanger_code_contre_token",
            return_value={
                "access_token": "meta-access",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        ), patch(
            "predictor.views.lister_comptes_publicitaires_meta",
            return_value=self.accounts,
        ):
            response = self.client.get(
                reverse(
                    "connecteur_oauth_callback",
                    args=["meta_ads"],
                ),
                {
                    "code": "code-meta",
                    "state": "state-meta",
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("selectionner_compte_meta_ads"),
            response["Location"],
        )
        self.assertEqual(
            CompteConnecteExterne.objects.filter(
                plateforme="meta_ads"
            ).count(),
            0,
        )
        flows = self.client.session.get(
            "meta_ads_oauth_flows",
            {},
        )
        self.assertEqual(len(flows), 1)
        pending = next(iter(flows.values()))
        self.assertEqual(
            [
                item["account_id"]
                for item in pending["comptes"]
            ],
            ["100", "200"],
        )
        self.assertNotEqual(
            pending["access_token_signe"],
            "meta-access",
        )

    def test_selection_page_displays_all_discovered_accounts(self):
        flow_id = self._seed_flow()

        response = self.client.get(
            reverse("selectionner_compte_meta_ads"),
            {"flow": flow_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Compte Meta A",
        )
        self.assertContains(
            response,
            "Compte Meta B",
        )
        self.assertEqual(
            CompteConnecteExterne.objects.filter(
                plateforme="meta_ads"
            ).count(),
            0,
        )

    def test_explicit_selection_creates_only_chosen_account(self):
        flow_id = self._seed_flow()

        response = self.client.post(
            reverse("selectionner_compte_meta_ads"),
            {
                "flow": flow_id,
                "account_id": "200",
            },
        )

        self.assertEqual(response.status_code, 302)
        comptes = CompteConnecteExterne.objects.filter(
            plateforme="meta_ads"
        )
        self.assertEqual(comptes.count(), 1)

        compte = comptes.get()
        self.assertEqual(
            compte.identifiant_externe,
            "200",
        )
        self.assertEqual(
            compte.nom_compte,
            "Compte Meta B",
        )
        self.assertEqual(
            compte.site,
            self.site,
        )
        self.assertEqual(
            compte.configuration["graph_id"],
            "act_200",
        )
        self.assertEqual(
            compte.configuration["devise"],
            "USD",
        )
        self.assertEqual(
            compte.configuration["fuseau_horaire"],
            "America/New_York",
        )
        self.assertEqual(
            self.client.session.get(
                "meta_ads_oauth_flows",
                {},
            ),
            {},
        )

    def test_unknown_account_id_is_refused(self):
        flow_id = self._seed_flow()

        response = self.client.post(
            reverse("selectionner_compte_meta_ads"),
            {
                "flow": flow_id,
                "account_id": "999",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            CompteConnecteExterne.objects.filter(
                plateforme="meta_ads"
            ).count(),
            0,
        )
        self.assertContains(
            response,
            "Sélection Meta Ads invalide",
        )

    def test_expired_flow_is_rejected_and_removed(self):
        expired_at = (
            timezone.now()
            - timedelta(minutes=16)
        ).timestamp()
        flow_id = self._seed_flow(
            created_at=expired_at
        )

        response = self.client.get(
            reverse("selectionner_compte_meta_ads"),
            {"flow": flow_id},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.client.session.get(
                "meta_ads_oauth_flows",
                {},
            ),
            {},
        )
        self.assertEqual(
            CompteConnecteExterne.objects.filter(
                plateforme="meta_ads"
            ).count(),
            0,
        )

    def test_flow_owned_by_another_user_is_rejected(self):
        flow_id = self._seed_flow(
            user_id=self.user.id + 999
        )

        response = self.client.get(
            reverse("selectionner_compte_meta_ads"),
            {"flow": flow_id},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            CompteConnecteExterne.objects.filter(
                plateforme="meta_ads"
            ).count(),
            0,
        )

    def test_disabled_site_is_rejected(self):
        flow_id = self._seed_flow()
        self.site.module_connecteurs_actif = False
        self.site.save(
            update_fields=[
                "module_connecteurs_actif"
            ]
        )

        response = self.client.get(
            reverse("selectionner_compte_meta_ads"),
            {"flow": flow_id},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            CompteConnecteExterne.objects.filter(
                plateforme="meta_ads"
            ).count(),
            0,
        )

    def test_existing_refresh_token_is_preserved_when_meta_returns_none(self):
        existing = CompteConnecteExterne.objects.create(
            client=self.pro,
            site=self.site,
            plateforme="meta_ads",
            nom_compte="Ancien compte",
            identifiant_externe="100",
            statut="connecte",
            refresh_token_signe=signer_token(
                "ancien-refresh"
            ),
        )
        old_refresh = existing.refresh_token_signe
        flow_id = self._seed_flow(
            refresh_token=""
        )

        response = self.client.post(
            reverse("selectionner_compte_meta_ads"),
            {
                "flow": flow_id,
                "account_id": "100",
            },
        )

        self.assertEqual(response.status_code, 302)
        existing.refresh_from_db()
        self.assertEqual(
            existing.refresh_token_signe,
            old_refresh,
        )
        self.assertEqual(
            existing.nom_compte,
            "Compte Meta A",
        )
