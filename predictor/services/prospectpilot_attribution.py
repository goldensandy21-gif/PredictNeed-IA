"""Capture et conservation du token d'attribution ProspectPilot (`ppt`).

`ppt` est un identifiant OPAQUE généré par ProspectPilot — on ne tente jamais
d'en déduire un prospect_id/campaign_id/email_id interne. PredictNeed se
contente de le conserver et de le renvoyer tel quel dans ses événements.

Règle d'attribution : first-touch. Si une session a déjà une attribution
active, l'arrivée d'un second token ProspectPilot dans la même session est
enregistrée (pour l'historique) mais ne remplace pas l'attribution retenue.
"""
import logging
import re

from django.utils import timezone

from ..models import ProspectPilotAttribution

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_\-]{8,128}$")
SESSION_KEY_NAME = "prospectpilot_attribution_id"


def _clean_token(raw_value):
    value = (raw_value or "").strip()
    if not value or not _TOKEN_RE.fullmatch(value):
        return ""
    return value


def capture_prospectpilot_attribution(request):
    """À appeler sur toute requête pouvant porter ?ppt=... . Ne casse jamais
    la page : toute erreur est journalisée et ignorée silencieusement."""
    token = _clean_token(request.GET.get("ppt", ""))
    if not token:
        return None

    try:
        if not request.session.session_key:
            request.session.create()
        session_key = request.session.session_key
        now = timezone.now()

        attribution, created = ProspectPilotAttribution.objects.get_or_create(
            token=token,
            defaults={
                "session_key": session_key,
                "landing_url": request.build_absolute_uri()[:2000],
                "utm_source": request.GET.get("utm_source", "")[:150],
                "utm_medium": request.GET.get("utm_medium", "")[:150],
                "utm_campaign": request.GET.get("utm_campaign", "")[:150],
                "utm_content": request.GET.get("utm_content", "")[:150],
            },
        )
        if not created:
            attribution.last_seen_at = now
            update_fields = ["last_seen_at"]
            if not attribution.session_key:
                attribution.session_key = session_key
                update_fields.append("session_key")
            attribution.save(update_fields=update_fields)

        # First-touch : on ne remplace jamais une attribution déjà retenue pour cette session.
        if not request.session.get(SESSION_KEY_NAME):
            request.session[SESSION_KEY_NAME] = attribution.pk

        return attribution
    except Exception:
        logger.exception("Capture de l'attribution ProspectPilot impossible (ppt=%r) — page non affectée.", token)
        return None


def get_current_attribution(request):
    """Retourne l'attribution first-touch de la session en cours, si connue."""
    try:
        attribution_id = request.session.get(SESSION_KEY_NAME)
        if attribution_id:
            attribution = ProspectPilotAttribution.objects.filter(pk=attribution_id, active=True).first()
            if attribution:
                return attribution
        session_key = request.session.session_key
        if session_key:
            return (
                ProspectPilotAttribution.objects.filter(session_key=session_key, active=True)
                .order_by("first_seen_at")
                .first()
            )
    except Exception:
        logger.exception("Lecture de l'attribution ProspectPilot impossible.")
    return None


def get_attribution_for_client(client_professionnel):
    """Utilisé après authentification (ex. paiement confirmé plus tard) quand
    la session anonyme d'origine n'est plus disponible."""
    if not client_professionnel:
        return None
    return client_professionnel.prospectpilot_attributions.filter(active=True).order_by("first_seen_at").first()
