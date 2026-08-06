
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
