# automation/management/commands/automation_scheduler.py
"""
Comando simples de scheduler para executar automações agendadas.

Uso:
    python manage.py automation_scheduler
    python manage.py automation_scheduler --interval 30

Ele roda em loop, a cada N segundos, verificando quais jobs
têm next_run_at vencido e disparando-os.
"""

import time
from django.core.management.base import BaseCommand
from automation.services import run_pending_jobs  # ⬅️ NOVO


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
                # Chama a função que dispara os jobs pendentes
                run_pending_jobs()
                time.sleep(interval)

        except KeyboardInterrupt:
            self.stdout.write(
                self.style.WARNING("Scheduler interrompido pelo usuário.")
            )
