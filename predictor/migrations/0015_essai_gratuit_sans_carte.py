
from datetime import timedelta

from django.db import migrations, models


def initialiser_anciens_essais(apps, schema_editor):
    ClientProfessionnel = apps.get_model(
        "predictor",
        "ClientProfessionnel",
    )

    for client in ClientProfessionnel.objects.filter(
        statut_abonnement="essai"
    ):
        debut = client.date_creation
        client.date_debut_essai = debut
        client.date_fin_essai = debut + timedelta(days=60)
        client.save(
            update_fields=[
                "date_debut_essai",
                "date_fin_essai",
            ]
        )


class Migration(migrations.Migration):
    dependencies = [
        ("predictor", "0014_siteclient_derniere_detection_script_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="clientprofessionnel",
            name="date_debut_essai",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="clientprofessionnel",
            name="date_fin_essai",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="clientprofessionnel",
            name="rappel_15_jours_envoye_le",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="clientprofessionnel",
            name="rappel_7_jours_envoye_le",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="clientprofessionnel",
            name="rappel_2_jours_envoye_le",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="clientprofessionnel",
            name="email_expiration_envoye_le",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="clientprofessionnel",
            name="statut_abonnement",
            field=models.CharField(
                choices=[
                    ("paiement_en_attente", "Paiement en attente"),
                    ("actif", "Actif"),
                    ("essai", "Essai"),
                    ("impaye", "Impayé"),
                    ("annule", "Annulé"),
                    ("expire", "Essai expiré"),
                ],
                default="essai",
                max_length=30,
            ),
        ),
        migrations.RunPython(
            initialiser_anciens_essais,
            migrations.RunPython.noop,
        ),
    ]
