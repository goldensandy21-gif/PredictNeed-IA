from django.conf import settings
from django.http import HttpResponsePermanentRedirect


class CanonicalDomainRedirectMiddleware:
    """
    Redirige l'ancien domaine Fly vers le domaine officiel PredictNeed IA.
    Le chemin et les paramètres de l'URL sont conservés.
    """

    OLD_HOST = "predictneed-ia.fly.dev"

    # Empêche une éventuelle redirection des contrôles de santé Fly.
    HEALTH_PATHS = {
        "/health",
        "/health/",
        "/healthz",
        "/healthz/",
        "/up",
        "/up/",
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(":", 1)[0].lower()

        if host == self.OLD_HOST and request.path not in self.HEALTH_PATHS:
            official_url = (
                settings.PREDICTNEED_SITE_URL
                or "https://predictneed-ia.com"
            ).rstrip("/")

            destination = f"{official_url}{request.get_full_path()}"

            # 301 pour les pages normales.
            # 308 pour les requêtes POST/PUT afin de préserver leur contenu.
            preserve_request = request.method not in {"GET", "HEAD"}

            return HttpResponsePermanentRedirect(
                destination,
                preserve_request=preserve_request,
            )

        return self.get_response(request)
