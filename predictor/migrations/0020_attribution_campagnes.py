from django.db import migrations, models


def backfill_opportunity_attribution(apps, schema_editor):
    OpportuniteCRM = apps.get_model("predictor", "OpportuniteCRM")

    queryset = (
        OpportuniteCRM.objects
        .filter(lead__isnull=False)
        .select_related("lead__session")
    )

    for opportunite in queryset.iterator():
        session = getattr(opportunite.lead, "session", None)

        if session is None or session.site_id != opportunite.site_id:
            continue

        details = {
            "utm_content": getattr(session, "utm_content", "") or "",
            "utm_term": getattr(session, "utm_term", "") or "",
            "utm_id": getattr(session, "utm_id", "") or "",
            "click_id_source": getattr(session, "click_id_source", "") or "",
            "click_id": getattr(session, "click_id", "") or "",
            "landing_page": getattr(session, "landing_page", "") or "",
            "referer": getattr(session, "referer", "") or "",
        }

        opportunite.source_attribution = session.source_visite or None
        opportunite.utm_source_attribution = session.utm_source or None
        opportunite.utm_medium_attribution = session.utm_medium or None
        opportunite.utm_campaign_attribution = session.utm_campaign or None
        opportunite.details_attribution = {
            key: value
            for key, value in details.items()
            if value
        }
        opportunite.save(
            update_fields=[
                "source_attribution",
                "utm_source_attribution",
                "utm_medium_attribution",
                "utm_campaign_attribution",
                "details_attribution",
            ]
        )


class Migration(migrations.Migration):

    dependencies = [
        ("predictor", "0019_connecteurs_uniques_par_site"),
    ]

    operations = [
        migrations.AddField(
            model_name="sessionvisiteur",
            name="utm_content",
            field=models.CharField(blank=True, max_length=150, null=True),
        ),
        migrations.AddField(
            model_name="sessionvisiteur",
            name="utm_term",
            field=models.CharField(blank=True, max_length=150, null=True),
        ),
        migrations.AddField(
            model_name="sessionvisiteur",
            name="utm_id",
            field=models.CharField(blank=True, max_length=150, null=True),
        ),
        migrations.AddField(
            model_name="sessionvisiteur",
            name="click_id_source",
            field=models.CharField(blank=True, max_length=40, null=True),
        ),
        migrations.AddField(
            model_name="sessionvisiteur",
            name="click_id",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="sessionvisiteur",
            name="landing_page",
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
        migrations.AddField(
            model_name="opportunitecrm",
            name="source_attribution",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="opportunitecrm",
            name="utm_source_attribution",
            field=models.CharField(blank=True, max_length=150, null=True),
        ),
        migrations.AddField(
            model_name="opportunitecrm",
            name="utm_medium_attribution",
            field=models.CharField(blank=True, max_length=150, null=True),
        ),
        migrations.AddField(
            model_name="opportunitecrm",
            name="utm_campaign_attribution",
            field=models.CharField(blank=True, max_length=150, null=True),
        ),
        migrations.AddField(
            model_name="opportunitecrm",
            name="details_attribution",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddIndex(
            model_name="sessionvisiteur",
            index=models.Index(
                fields=["site", "utm_campaign"],
                name="session_site_campaign_idx",
            ),
        ),
        migrations.RunPython(
            backfill_opportunity_attribution,
            migrations.RunPython.noop,
        ),
    ]
