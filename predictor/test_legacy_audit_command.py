from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from .models import (
    AutomatisationEmail,
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
class LegacyAuditCommandTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="legacy-owner",
            email="legacy@example.com",
            password="MotDePasse-Solide-2026!",
        )
        self.client_pro = ClientProfessionnel.objects.create(
            utilisateur=self.user,
            nom_entreprise="Legacy Corp",
            statut_abonnement="actif",
        )
        self.site = SiteClient.objects.create(
            client=self.client_pro,
            nom_site="Site legacy",
            domaine="legacy.example",
            actif=True,
        )

    def test_legacy_audit_reports_site_less_records_without_writing(self):
        CompteConnecteExterne.objects.create(
            client=self.client_pro,
            site=None,
            plateforme="google_ads",
            nom_compte="Connecteur global historique",
        )
        AutomatisationEmail.objects.create(
            client=self.client_pro,
            site=None,
            nom="Automation globale historique",
        )

        output = StringIO()
        call_command("auditer_donnees_legacy", stdout=output)

        text = output.getvalue()
        self.assertIn("connecteurs_sans_site: 1", text)
        self.assertIn("automatisations_sans_site: 1", text)
        self.assertEqual(
            CompteConnecteExterne.objects.filter(site__isnull=True).count(),
            1,
        )
        self.assertEqual(
            AutomatisationEmail.objects.filter(site__isnull=True).count(),
            1,
        )

    def test_legacy_audit_can_fail_on_issues(self):
        AutomatisationEmail.objects.create(
            client=self.client_pro,
            site=None,
            nom="Automation globale historique",
        )

        with self.assertRaises(CommandError):
            call_command(
                "auditer_donnees_legacy",
                fail_on_issues=True,
                stdout=StringIO(),
            )
