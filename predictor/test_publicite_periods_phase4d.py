from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    ClientProfessionnel,
    SiteClient,
)


@override_settings(
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
)
class PublicitePeriodsPhase4DTests(TestCase):

    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            username="publicite-periods",
            email="publicite-periods@example.com",
            password="Test-2026-solide!",
        )

        self.client_pro = ClientProfessionnel.objects.create(
            utilisateur=self.user,
            nom_entreprise="Entreprise Publicité",
            statut_abonnement="actif",
        )

        self.site = SiteClient.objects.create(
            client=self.client_pro,
            nom_site="Site Publicité",
            domaine="publicite.example",
            actif=True,
            module_publicite_actif=True,
        )

        self.client.force_login(self.user)

    def test_publicite_utilise_30_jours_par_defaut(self):
        response = self.client.get(
            reverse("module_publicite"),
            {
                "site": self.site.id,
            },
        )

        self.assertEqual(response.status_code, 200)

        fin = (
            timezone.localdate()
            - timedelta(days=1)
        )

        debut = fin - timedelta(days=29)

        self.assertEqual(
            response.context["periode_pub"],
            "30j",
        )

        self.assertEqual(
            response.context["date_debut_obj"],
            debut,
        )

        self.assertEqual(
            response.context["date_fin_obj"],
            fin,
        )

        self.assertContains(
            response,
            "30 jours",
        )

        self.assertContains(
            response,
            "Historique disponible",
        )

    def test_publicite_historique_utilise_limite_11_ans(self):
        response = self.client.get(
            reverse("module_publicite"),
            {
                "site": self.site.id,
                "periode_pub": "historique",
            },
        )

        self.assertEqual(response.status_code, 200)

        fin = (
            timezone.localdate()
            - timedelta(days=1)
        )

        total = (
            fin.year * 12
            + (fin.month - 1)
            - 131
        )

        annee, mois_zero = divmod(
            total,
            12,
        )

        debut_attendu = date(
            annee,
            mois_zero + 1,
            1,
        )

        self.assertEqual(
            response.context["periode_pub"],
            "historique",
        )

        self.assertEqual(
            response.context["date_debut_obj"],
            debut_attendu,
        )

        self.assertIn(
            "mensuelle",
            response.context[
                "periode_granularite"
            ].lower(),
        )

        self.assertContains(
            response,
            "Configuration actuelle des conversions Google Ads",
        )
