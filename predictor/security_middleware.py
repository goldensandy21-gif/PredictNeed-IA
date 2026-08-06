
import json

from django.http import JsonResponse
from django.shortcuts import render
from django.utils.deprecation import MiddlewareMixin

from .security import consume_rate_limit


class PublicRateLimitMiddleware(MiddlewareMixin):
    RULES = {
        "connexion": (10, 900, "form"),
        "inscription": (5, 3600, "form"),
        "password_reset": (5, 3600, "form"),
        "contact": (5, 3600, "form"),
        "newsletter_inscription": (5, 3600, "form"),
        "capture_lead": (20, 3600, "api"),
        "tracker_installation_ping": (120, 300, "api"),
    }

    def process_view(self, request, view_func, view_args, view_kwargs):
        match = getattr(request, "resolver_match", None)
        route_name = match.url_name if match is not None else None
        rule = self.RULES.get(route_name)
        if rule is None:
            return None

        if route_name == "tracker_installation_ping":
            if request.method != "GET":
                return None
        elif request.method != "POST":
            return None

        limit, window, response_type = rule
        identifier = ""
        if response_type == "form" and route_name in {"connexion", "password_reset"}:
            identifier = (
                request.POST.get("username")
                or request.POST.get("email")
                or ""
            )
        elif request.body and len(request.body) <= 32768:
            try:
                payload = json.loads(request.body.decode("utf-8"))
                identifier = payload.get("api_key") or payload.get("email") or ""
            except (json.JSONDecodeError, UnicodeDecodeError):
                identifier = ""

        allowed, retry = consume_rate_limit(
            action=route_name,
            request=request,
            limit=limit,
            window_seconds=window,
            identifier=identifier,
        )
        if allowed:
            return None

        if response_type == "api":
            response = JsonResponse(
                {
                    "success": False,
                    "error": "Trop de demandes. Merci de réessayer plus tard.",
                },
                status=429,
            )
        else:
            response = render(
                request,
                "predictor/429.html",
                status=429,
            )
        response["Retry-After"] = str(retry)
        return response
