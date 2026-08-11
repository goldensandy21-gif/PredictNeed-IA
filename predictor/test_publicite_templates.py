from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import ClientProfessionnel, SiteClient


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
class PubliciteTemplateTests(TestCase):

    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            username="template-publicite",
            password="Test-2026!",
        )

        self.client_pro = ClientProfessionnel.objects.create(
            utilisateur=self.user,
            nom_entreprise="Test Templates",
            statut_abonnement="actif",
        )

        self.site = SiteClient.objects.create(
            client=self.client_pro,
            nom_site="Site Templates",
            domaine="templates.example",
            actif=True,
            module_publicite_actif=True,
        )

        self.client.login(
            username="template-publicite",
            password="Test-2026!",
        )

    def test_un_template_propre_par_regie(self):
        templates = {
            "google_ads": "predictor/module_publicite.html",
            "meta_ads": "predictor/module_publicite_meta.html",
            "tiktok_ads": "predictor/module_publicite_tiktok.html",
            "linkedin_ads": "predictor/module_publicite_linkedin.html",
        }

        for plateforme, template in templates.items():
            with self.subTest(plateforme=plateforme):
                response = self.client.get(
                    reverse("module_publicite"),
                    {
                        "site": self.site.id,
                        "plateforme_pub": plateforme,
                    },
                )

                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, template)
