
from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from predictor.models import JournalMaintenance


class Command(BaseCommand):
    help = (
        "Exécute la maintenance quotidienne : essais gratuits, purge RGPD "
        "et nettoyage des anciennes limitations de sécurité."
    )

    def handle(self, *args, **options):
        journal = JournalMaintenance.objects.create(
            type_operation="maintenance_quotidienne",
            statut="en_cours",
        )
        details = {}

        steps = [
            (
                "essais",
                "gerer_essais_gratuits",
                {},
            ),
            (
                "purge_rgpd",
                "purge_donnees_rgpd",
                {
                    "execute": True,
                    "analytics_days": (
                        settings.PREDICTNEED_ANALYTICS_RETENTION_DAYS
                    ),
                    "lead_days": settings.PREDICTNEED_LEAD_RETENTION_DAYS,
                },
            ),
            (
                "securite",
                "nettoyer_limitations_securite",
                {},
            ),
        ]

        try:
            for key, command_name, command_options in steps:
                buffer = StringIO()
                call_command(
                    command_name,
                    stdout=buffer,
                    **command_options,
                )
                output = buffer.getvalue().strip()
                details[key] = {
                    "commande": command_name,
                    "sortie": output,
                }
                if output:
                    self.stdout.write(output)

            journal.statut = "succes"
            journal.details = details
            journal.date_fin = timezone.now()
            journal.save(
                update_fields=["statut", "details", "date_fin"]
            )
            self.stdout.write(
                self.style.SUCCESS(
                    "Maintenance quotidienne terminée sans erreur."
                )
            )
        except Exception as exc:
            journal.statut = "erreur"
            journal.details = details
            journal.message_erreur = str(exc)[:4000]
            journal.date_fin = timezone.now()
            journal.save(
                update_fields=[
                    "statut",
                    "details",
                    "message_erreur",
                    "date_fin",
                ]
            )
            raise CommandError(str(exc)) from exc
