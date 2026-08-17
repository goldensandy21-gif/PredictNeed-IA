import logging

from .services.prospectpilot_attribution import capture_prospectpilot_attribution
from .services.prospectpilot_events import send_prospectpilot_event

logger = logging.getLogger(__name__)


class ProspectPilotAttributionMiddleware:
    """Capture ?ppt=... sur toute page d'arrivée et journalise product_visited
    une seule fois par attribution. Coût nul pour les requêtes sans `ppt`."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        attribution = None
        if request.method == "GET" and request.GET.get("ppt"):
            attribution = capture_prospectpilot_attribution(request)

        response = self.get_response(request)

        if attribution and not attribution.product_visited_sent:
            try:
                send_prospectpilot_event(
                    "product_visited",
                    attribution=attribution,
                    idempotency_key=f"{attribution.token}:product_visited",
                    metadata={"landing_url": attribution.landing_url},
                )
                attribution.product_visited_sent = True
                attribution.save(update_fields=["product_visited_sent"])
            except Exception:
                logger.exception("Notification product_visited impossible — navigation non affectée.")

        return response
