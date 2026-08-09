
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from .models import NewsletterInscription

TEST_STORAGES = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}

@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", STORAGES=TEST_STORAGES, PREDICTNEED_SITE_URL="https://predictneed-ia.com", PREDICTNEED_CONTACT_EMAIL="contact@example.com")
class PublicLaunchTests(TestCase):
    def test_sitemap_has_no_fake_lastmod(self):
        text = self.client.get(reverse("sitemap_xml")).content.decode()
        self.assertIn("https://predictneed-ia.com/", text)
        self.assertNotIn("<lastmod>", text)
    def test_robots_points_to_canonical_sitemap_and_blocks_private_routes(self):
        text = self.client.get(reverse("robots_txt")).content.decode()
        self.assertIn("Sitemap: https://predictneed-ia.com/sitemap.xml", text)
        self.assertIn("Disallow: /dashboard/", text)
        self.assertIn("Disallow: /api/", text)
        self.assertIn("Disallow: /stripe/", text)
    def test_public_home_has_canonical_domain(self):
        self.assertContains(
            self.client.get(reverse("accueil")),
            'rel="canonical" href="https://predictneed-ia.com/"',
        )
    @override_settings(GOOGLE_SITE_VERIFICATION="google-test-token")
    def test_google_site_verification_meta_is_optional(self):
        self.assertContains(
            self.client.get(reverse("accueil")),
            'name="google-site-verification" content="google-test-token"',
        )
    def test_login_is_noindex(self):
        self.assertContains(self.client.get(reverse("connexion")), 'content="noindex,follow"')
    def test_newsletter_double_confirmation(self):
        self.client.post(reverse("newsletter_inscription"), {"email":"guide@example.com", "guides_consent":"on", "next":"/"})
        item = NewsletterInscription.objects.get(email="guide@example.com")
        self.assertEqual(item.statut, "en_attente")
        self.assertEqual(len(mail.outbox), 1)
        self.client.get(reverse("newsletter_confirmer", args=[item.token]))
        item.refresh_from_db()
        self.assertEqual(item.statut, "confirmee")
    def test_health(self):
        self.assertEqual(self.client.get(reverse("health_check")).status_code, 200)
