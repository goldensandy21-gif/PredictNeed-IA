from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("predictor", "0018_machine_learning_et_maintenance"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="compteconnecteexterne",
            constraint=models.UniqueConstraint(
                fields=(
                    "client",
                    "site",
                    "plateforme",
                    "identifiant_externe",
                ),
                condition=models.Q(
                    site__isnull=False,
                    identifiant_externe__isnull=False,
                ),
                name="connecteur_externe_unique_par_site",
            ),
        ),
    ]
