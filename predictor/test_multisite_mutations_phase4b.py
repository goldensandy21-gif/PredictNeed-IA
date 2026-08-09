from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import (
    AutomatisationEmail,
    ClientProfessionnel,
    LeadCapture,
    SessionVisiteur,
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
class MultiSiteMutationSafetyTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="mutation-owner",
            email="mutation@example.com",
            password="MotDePasse-Solide-2026!",
        )
        self.pro = ClientProfessionnel.objects.create(
            utilisateur=self.user,
            nom_entreprise="Mutation Corp",
            statut_abonnement="actif",
        )
        self.site_a = SiteClient.objects.create(
            client=self.pro,
            nom_site="Site A",
            domaine="a-mutation.example",
            actif=True,
        )
        self.site_b = SiteClient.objects.create(
            client=self.pro,
            nom_site="Site B",
            domaine="b-mutation.example",
            actif=True,
        )
        self.session_a = SessionVisiteur.objects.create(
            site=self.site_a,
            session_id="mutation-session-a",
        )
        self.session_b = SessionVisiteur.objects.create(
            site=self.site_b,
            session_id="mutation-session-b",
        )
        self.lead_a = LeadCapture.objects.create(
            site=self.site_a,
            session=self.session_a,
            email="lead-a@example.com",
            consentement=True,
            statut_suivi="nouveau",
        )
        self.lead_b = LeadCapture.objects.create(
            site=self.site_b,
            session=self.session_b,
            email="lead-b@example.com",
            consentement=True,
            statut_suivi="nouveau",
        )
        self.auto_a = AutomatisationEmail.objects.create(
            client=self.pro,
            site=self.site_a,
            nom="Automation A",
            sujet="Sujet A",
            contenu="Contenu A",
        )
        self.auto_b = AutomatisationEmail.objects.create(
            client=self.pro,
            site=self.site_b,
            nom="Automation B",
            sujet="Sujet B",
            contenu="Contenu B",
        )
        self.client.force_login(self.user)

    def test_lead_status_requires_selected_site(self):
        response = self.client.post(
            reverse(
                "changer_statut_lead",
                args=[self.lead_a.id, "contacte"],
            )
        )

        self.assertEqual(response.status_code, 400)
        self.lead_a.refresh_from_db()
        self.assertEqual(self.lead_a.statut_suivi, "nouveau")

    def test_lead_status_changes_only_selected_site(self):
        response = self.client.post(
            reverse(
                "changer_statut_lead",
                args=[self.lead_a.id, "contacte"],
            ),
            {"site": str(self.site_a.id)},
        )

        self.assertEqual(response.status_code, 200)
        self.lead_a.refresh_from_db()
        self.assertEqual(self.lead_a.statut_suivi, "contacte")

    def test_lead_from_other_owned_site_cannot_be_changed(self):
        response = self.client.post(
            reverse(
                "changer_statut_lead",
                args=[self.lead_b.id, "converti"],
            ),
            {"site": str(self.site_a.id)},
        )

        self.assertEqual(response.status_code, 404)
        self.lead_b.refresh_from_db()
        self.assertEqual(self.lead_b.statut_suivi, "nouveau")

    def test_automation_requires_selected_site(self):
        response = self.client.post(
            reverse(
                "modifier_automatisation_email",
                args=[self.auto_a.id],
            ),
            {
                "nom": "Nom modifié",
                "sujet": "Sujet modifié",
                "contenu": "Contenu modifié",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.auto_a.refresh_from_db()
        self.assertEqual(self.auto_a.nom, "Automation A")

    def test_automation_changes_only_selected_site(self):
        response = self.client.post(
            reverse(
                "modifier_automatisation_email",
                args=[self.auto_a.id],
            ),
            {
                "site": str(self.site_a.id),
                "nom": "Automation A modifiée",
                "sujet": "Sujet A modifié",
                "contenu": "Contenu A modifié",
                "actif": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.auto_a.refresh_from_db()
        self.assertEqual(
            self.auto_a.nom,
            "Automation A modifiée",
        )

    def test_automation_from_other_owned_site_cannot_be_changed(self):
        response = self.client.post(
            reverse(
                "modifier_automatisation_email",
                args=[self.auto_b.id],
            ),
            {
                "site": str(self.site_a.id),
                "nom": "Tentative croisée",
                "sujet": "Tentative croisée",
                "contenu": "Tentative croisée",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.auto_b.refresh_from_db()
        self.assertEqual(self.auto_b.nom, "Automation B")

    def test_dashboard_propagates_selected_site_to_mutations(self):
        response = self.client.get(
            reverse("dashboard"),
            {"site": str(self.site_a.id)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'const selectedSiteId = "{self.site_a.id}";',
        )
        self.assertContains(
            response,
            (
                '<input type="hidden" name="site" '
                f'value="{self.site_a.id}">'
            ),
        )
