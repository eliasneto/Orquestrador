# automation/management/commands/automation_scheduler.py
"""
Comando simples de scheduler para executar automações agendadas.

Uso:
    python manage.py automation_scheduler
    python manage.py automation_scheduler --interval 30

Ele roda em loop, a cada N segundos, verificando quais jobs
estão "vencidos" (job.is_due(now)) e executando-os.
"""

import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from automation.models import AutomationJob
from automation.services import execute_job


class Command(BaseCommand):
    help = "Loop simples de agendamento para o módulo de automação."

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=int,
            default=60,
            help="Intervalo (em segundos) entre as verificações. Default: 60.",
        )

    def handle(self, *args, **options):
        interval = options["interval"]
        self.stdout.write(
            self.style.SUCCESS(
                f"Iniciando automation_scheduler (intervalo={interval}s)..."
            )
        )

        try:
            while True:
                now = timezone.now()
                jobs = AutomationJob.objects.filter(is_enabled=True)

                for job in jobs:
                    if job.is_due(now):
                        self.stdout.write(
                            self.style.WARNING(
                                f"Executando job {job.id} - {job.name}"
                            )
                        )
                        execute_job(job, triggered_by=None)

                time.sleep(interval)

        except KeyboardInterrupt:
            self.stdout.write(
                self.style.WARNING("Scheduler interrompido pelo usuário.")
            )
