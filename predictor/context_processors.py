
import json
from django.conf import settings
from django.templatetags.static import static

NOINDEX = {
    "connexion",
    "inscription",
    "deconnexion",
    "paiement_succes",
    "paiement_annule",
    "dashboard",
    "dashboard_parametres",
    "newsletter_confirmer",
    "newsletter_desinscription",
    "confirmer_email_compte",
    "password_reset",
    "password_reset_done",
    "password_reset_confirm",
    "password_reset_complete",
}


def global_site_context(request):
    base = (settings.PREDICTNEED_SITE_URL or request.build_absolute_uri("/").rstrip("/")).rstrip("/")
    route = request.resolver_match.url_name if request.resolver_match else ""
    graph = []
    if route == "accueil":
        graph = [
            {"@type": "Organization", "name": "PredictNeed IA", "url": base, "email": settings.PREDICTNEED_CONTACT_EMAIL},
            {"@type": "WebSite", "name": "PredictNeed IA", "url": base},
            {"@type": "SoftwareApplication", "name": "PredictNeed IA Pro", "applicationCategory": "BusinessApplication", "operatingSystem": "Web", "url": base, "offers": {"@type": "Offer", "price": f"{settings.PREDICTNEED_SUBSCRIPTION_PRICE_CENTS/100:.2f}", "priceCurrency": "EUR"}},
        ]
    schema = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False) if graph else ""
    return {
        "canonical_url": f"{base}{request.path}",
        "social_image_url": f"{base}{static('predictor/home-hero-dashboard.png')}",
        "google_site_verification": settings.GOOGLE_SITE_VERIFICATION,
        "robots_meta": "noindex,follow" if route in NOINDEX else "index,follow",
        "structured_data_json": schema,
    }
