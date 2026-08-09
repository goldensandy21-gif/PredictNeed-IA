from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("predictor", "0022_mesures_regies_journalieres"),
    ]

    operations = [
        migrations.AlterField(
            model_name="campagneexterne",
            name="conversions",
            field=models.DecimalField(
                decimal_places=4,
                default=0,
                max_digits=14,
            ),
        ),
    ]
