
from django.conf import settings
from django.http import HttpResponsePermanentRedirect

class CanonicalDomainRedirectMiddleware:
    ALIAS_HOSTS = {"predictneed-ia.fly.dev", "www.predictneed-ia.com"}
    HEALTH_PATHS = {"/healthz", "/healthz/"}
    def __init__(self, get_response): self.get_response = get_response
    def __call__(self, request):
        host = request.get_host().split(":", 1)[0].lower()
        if host in self.ALIAS_HOSTS and request.path not in self.HEALTH_PATHS:
            base = (settings.PREDICTNEED_SITE_URL or "https://predictneed-ia.com").rstrip("/")
            return HttpResponsePermanentRedirect(f"{base}{request.get_full_path()}", preserve_request=request.method not in {"GET", "HEAD"})
        return self.get_response(request)
