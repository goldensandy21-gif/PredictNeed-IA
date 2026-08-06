
from django.db import migrations, models


def initialiser_preuves_comptes_existants(apps, schema_editor):
    ClientProfessionnel = apps.get_model("predictor", "ClientProfessionnel")
    for client in ClientProfessionnel.objects.select_related("utilisateur").all():
        champs = []
        if not client.version_cgu_acceptee:
            client.version_cgu_acceptee = "2026-08-06"
            champs.append("version_cgu_acceptee")
        if not client.version_confidentialite_acceptee:
            client.version_confidentialite_acceptee = "2026-08-06"
            champs.append("version_confidentialite_acceptee")
        if client.utilisateur.is_active and client.email_verifie_le is None:
            client.email_verifie_le = client.date_creation
            champs.append("email_verifie_le")
        if champs:
            client.save(update_fields=champs)


class Migration(migrations.Migration):
    dependencies = [
        ("predictor", "0016_newsletter_seo_lancement"),
    ]

    operations = [
        migrations.AddField(
            model_name="clientprofessionnel",
            name="email_verifie_le",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="clientprofessionnel",
            name="version_cgu_acceptee",
            field=models.CharField(blank=True, default="", max_length=30),
        ),
        migrations.AddField(
            model_name="clientprofessionnel",
            name="version_confidentialite_acceptee",
            field=models.CharField(blank=True, default="", max_length=30),
        ),
        migrations.AlterField(
            model_name="sessionvisiteur",
            name="session_id",
            field=models.CharField(max_length=100),
        ),
        migrations.AddConstraint(
            model_name="sessionvisiteur",
            constraint=models.UniqueConstraint(
                fields=("site", "session_id"),
                name="session_unique_par_site",
            ),
        ),
        migrations.AddConstraint(
            model_name="sessionvisiteur",
            constraint=models.UniqueConstraint(
                condition=models.Q(site__isnull=True),
                fields=("session_id",),
                name="session_publique_unique_sans_site",
            ),
        ),
        migrations.CreateModel(
            name="LimitationSecurite",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("action", models.CharField(max_length=80)),
                ("cle_hachee", models.CharField(max_length=64)),
                ("debut_fenetre", models.DateTimeField()),
                ("compteur", models.PositiveIntegerField(default=0)),
                ("derniere_tentative", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddConstraint(
            model_name="limitationsecurite",
            constraint=models.UniqueConstraint(
                fields=("action", "cle_hachee"),
                name="limitation_unique_action_cle",
            ),
        ),
        migrations.AddIndex(
            model_name="limitationsecurite",
            index=models.Index(
                fields=["action", "debut_fenetre"],
                name="limite_action_fenetre_idx",
            ),
        ),
        migrations.RunPython(
            initialiser_preuves_comptes_existants,
            migrations.RunPython.noop,
        ),
    ]
