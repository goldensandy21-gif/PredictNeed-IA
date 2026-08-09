from __future__ import annotations


def extraire_attribution_session(session):
    if session is None:
        return {
            "source": "",
            "utm_source": "",
            "utm_medium": "",
            "utm_campaign": "",
            "details": {},
        }

    return {
        "source": session.source_visite or "",
        "utm_source": session.utm_source or "",
        "utm_medium": session.utm_medium or "",
        "utm_campaign": session.utm_campaign or "",
        "details": {
            "utm_content": session.utm_content or "",
            "utm_term": session.utm_term or "",
            "utm_id": session.utm_id or "",
            "click_id_source": session.click_id_source or "",
            "click_id": session.click_id or "",
            "landing_page": session.landing_page or "",
            "referer": session.referer or "",
        },
    }


def appliquer_attribution_opportunite(opportunite, *, force=False):
    lead = opportunite.lead
    session = getattr(lead, "session", None) if lead is not None else None

    if session is None or session.site_id != opportunite.site_id:
        return opportunite

    attribution = extraire_attribution_session(session)
    fields = []

    mapping = {
        "source_attribution": attribution["source"],
        "utm_source_attribution": attribution["utm_source"],
        "utm_medium_attribution": attribution["utm_medium"],
        "utm_campaign_attribution": attribution["utm_campaign"],
    }

    for field_name, value in mapping.items():
        if value and (force or not getattr(opportunite, field_name)):
            setattr(opportunite, field_name, value)
            fields.append(field_name)

    current_details = dict(opportunite.details_attribution or {})
    new_details = dict(current_details)

    for key, value in attribution["details"].items():
        if value and (force or not new_details.get(key)):
            new_details[key] = value

    if new_details != current_details:
        opportunite.details_attribution = new_details
        fields.append("details_attribution")

    if fields:
        fields.append("date_mise_a_jour")
        opportunite.save(update_fields=fields)

    return opportunite
