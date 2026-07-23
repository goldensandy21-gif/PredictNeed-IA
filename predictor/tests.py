from django.contrib.auth import get_user_model
from django.test import override_settings
from django.test import TestCase
from django.urls import reverse
from html import unescape

from .models import ClientProfessionnel, SiteClient


@override_settings(STORAGES={
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
})
class RetargetingConnectorsTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="cliente",
            email="cliente@example.com",
            password="secret-test",
        )
        self.client_pro = ClientProfessionnel.objects.create(
            utilisateur=self.user,
            nom_entreprise="Client Test",
        )
        self.site = SiteClient.objects.create(
            client=self.client_pro,
            nom_site="Site Test",
            domaine="example.com",
            module_connecteurs_actif=True,
            retargeting_actif=True,
            meta_pixel_id="123456789",
            google_ads_id="AW-123456789",
            google_ads_conversion_label="LeadLabel",
            tiktok_pixel_id="CABC123",
            linkedin_partner_id="987654",
            linkedin_conversion_id="456789",
            pinterest_tag_id="2612345678901",
        )

    def test_module_connecteurs_inclut_les_ids_retargeting_dans_le_script(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("module_connecteurs"))
        content = unescape(response.content.decode())

        self.assertIn('data-retargeting-enabled="true"', content)
        self.assertIn('data-meta-pixel-id="123456789"', content)
        self.assertIn('data-google-ads-id="AW-123456789"', content)
        self.assertIn('data-google-ads-conversion-label="LeadLabel"', content)
        self.assertIn('data-tiktok-pixel-id="CABC123"', content)
        self.assertIn('data-linkedin-partner-id="987654"', content)
        self.assertIn('data-linkedin-conversion-id="456789"', content)
        self.assertIn('data-pinterest-tag-id="2612345678901"', content)

    def test_module_connecteurs_masque_la_configuration_interne_au_client(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("module_connecteurs"))
        content = response.content.decode()

        self.assertNotContains(response, "Configuration interne administrateur")
        self.assertNotContains(response, "Stripe / Paiement")
        self.assertNotContains(response, "Django Admin")
        self.assertNotContains(response, "Comptes publicitaires à connecter")
        self.assertNotContains(response, "Connexion OAuth pour lire les comptes")
        self.assertNotContains(response, "Connexion bientôt disponible")
        self.assertIn("Pixels de retargeting", content)
        self.assertIn("Scripts d’installation", content)

    def test_mise_a_jour_retargeting_nettoie_les_identifiants(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("mettre_a_jour_retargeting_site", args=[self.site.id]),
            {
                "retargeting_actif": "on",
                "meta_pixel_id": '123"><script>',
                "google_ads_id": "AW-123 456",
                "google_ads_conversion_label": "Lead/Label_01",
                "tiktok_pixel_id": "TTQ:ABC",
                "linkedin_partner_id": "987 654",
                "linkedin_conversion_id": "conv-456",
                "pinterest_tag_id": "pin.123",
            },
        )

        self.assertRedirects(response, f"{reverse('module_connecteurs')}?site={self.site.id}")
        self.site.refresh_from_db()
        self.assertTrue(self.site.retargeting_actif)
        self.assertEqual(self.site.meta_pixel_id, "123script")
        self.assertEqual(self.site.google_ads_id, "AW-123456")
        self.assertEqual(self.site.google_ads_conversion_label, "Lead/Label_01")
        self.assertEqual(self.site.tiktok_pixel_id, "TTQ:ABC")
        self.assertEqual(self.site.linkedin_partner_id, "987654")
        self.assertEqual(self.site.linkedin_conversion_id, "conv-456")
        self.assertEqual(self.site.pinterest_tag_id, "pin.123")

    def test_guide_utilisation_est_public_et_lie_depuis_le_footer(self):
        response = self.client.get(reverse("guide_utilisation"))

        self.assertContains(response, "Guide d'utilisation et glossaire PredictNeed IA")
        self.assertContains(response, "Dashboard")
        self.assertContains(response, "Retargeting")
        self.assertContains(response, "Glossaire")
        self.assertContains(response, reverse("guide_utilisation"))
