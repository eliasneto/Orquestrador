# automation/models.py
"""
Modelos principais do módulo de automação.

Aqui definimos:
- AutomationJob: cadastro de cada automação (o “que” e “quando”).
- AutomationRun: histórico de execuções (o “quando rodou” e “como foi”).
"""

import datetime as dt

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.conf import settings
from pathlib import Path
User = get_user_model()


# automation/models.py
import datetime as dt
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

User = get_user_model()


# automation/models.py
import datetime as dt
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

User = get_user_model()


# automation/models.py
import datetime as dt
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

User = get_user_model()


class AutomationJob(models.Model):
    class ScheduleType(models.TextChoices):
        ONCE = "once", "Pontual"
        DAILY = "daily", "Diário"

    # 🔹 NOVO: tipos de setor
    class Sector(models.TextChoices):
        GERAL = "geral", "Geral"
        FINANCEIRO = "financeiro", "Financeiro"
        COMERCIAL = "comercial", "Comercial"
        TI = "ti", "TI"
        # pode ir acrescentando mais se precisar        

    name = models.CharField("Nome da automação", max_length=200)

    description = models.TextField(
        "Descrição",
        blank=True,
        help_text="Explicação rápida do que essa automação faz (aparece só na interface).",
    )

    code = models.SlugField(
        "Código interno",
        max_length=100,
        unique=True,
        help_text="Identificador curto, sem espaços. Ex: robo_ixc_login_cliente",
    )

    # 🔹 NOVO: setor da automação
    sector = models.CharField(
       "Setor",
        max_length=50,
        choices=Sector.choices,
        default=Sector.GERAL,
        help_text="Setor responsável pela automação (usado para filtros futuros).",
    )

    # Arquivo Python dentro da pasta automation_jobs/job_<id>/
    external_main_script = models.CharField(
        "Arquivo principal (Python)",
        max_length=200,
        default="main.py",
        help_text="Ex: main.py, app.py – arquivo dentro da pasta da automação.",
    )

    is_active = models.BooleanField("Ativa", default=True)
    allow_manual = models.BooleanField("Permite disparo manual", default=True)

    # Agendamento bem simples
    schedule_type = models.CharField(
        "Tipo de agendamento",
        max_length=20,
        choices=ScheduleType.choices,
        default=ScheduleType.ONCE,
    )

    # Para execução pontual
    one_off_run_at = models.DateTimeField(
        "Data/hora (pontual)",
        null=True,
        blank=True,
    )

    # Para execução diária
    daily_time = models.TimeField(
        "Horário diário",
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Automação"
        verbose_name_plural = "Automações"

    def __str__(self) -> str:
        return self.name

    # Pasta física da automação: automation_jobs/job_<id>/
    def get_job_dir(self) -> Path:
        """
        Pasta física da automação: automation_jobs/job_<id>/
        Já garante também as subpastas 'entrada' e 'saida'.
        """
        base = Path(settings.BASE_DIR) / "automation_jobs" / f"job_{self.pk}"
        base.mkdir(parents=True, exist_ok=True)

        # subpastas padrão
        (base / "entrada").mkdir(exist_ok=True)
        (base / "saida").mkdir(exist_ok=True)

        return base


    @property
    def workspace_folder_name(self) -> str:
        """
        Nome da pasta local que será usada como workspace da automação.
        Só para exibição.
        """
        return f"job_{self.pk or 'novo'}"

    # ---------- Descrição “bonita” do agendamento ----------
    @property
    def schedule_description(self) -> str:
        if self.schedule_type == self.ScheduleType.DAILY:
            if self.daily_time:
                return f"Diária às {self.daily_time.strftime('%H:%M')}"
            return "Diária (sem horário definido)"

        if self.schedule_type == self.ScheduleType.ONCE:
            if self.one_off_run_at:
                dt_local = timezone.localtime(self.one_off_run_at)
                return f"Pontual em {dt_local.strftime('%d/%m/%Y %H:%M')}"
            return "Pontual (sem data definida)"

        return "-"

    def next_run_display(self) -> str:
        """
        Texto simples para a coluna 'Próxima execução' na lista.
        """
        if not self.is_active:
            return "Desativada"

        if self.schedule_type == self.ScheduleType.ONCE:
            if not self.one_off_run_at:
                return "Sem data"
            return timezone.localtime(self.one_off_run_at).strftime("%d/%m/%Y %H:%M")

        if self.schedule_type == self.ScheduleType.DAILY:
            if not self.daily_time:
                return "Horário não definido"
            return self.daily_time.strftime("%H:%M")

        return "-"
    
    @property
    def has_running(self) -> bool:
        """
        Indica se existe alguma execução desta automação ainda em andamento.
        Usa a anotação 'runs_running' se ela existir (lista), senão consulta direto.
        """
        value = getattr(self, "runs_running", None)
        if value is not None:
            return value > 0

        from .models import AutomationRun  # evita import circular
        return self.runs.filter(status=AutomationRun.Status.RUNNING).exists()    

    # Hoje o scheduler ainda não está usando isso – deixo falso para não confundir.
    def is_due(self, now: dt.datetime) -> bool:
        return False




class AutomationRun(models.Model):
    """
    Histórico de execuções de uma automação.

    Cada vez que um job roda, criamos um AutomationRun:
    - quando iniciou
    - quando terminou
    - status (success, failed, running)
    - log (stdout + erros)
    """

    class Status(models.TextChoices):
        RUNNING = "running", "Em execução"
        SUCCESS = "success", "Sucesso"
        FAILED = "failed", "Falhou"

    class TriggerMode(models.TextChoices):
        SCHEDULE = "schedule", "Agendado"
        MANUAL = "manual", "Manual"

    job = models.ForeignKey(
        AutomationJob,
        on_delete=models.CASCADE,
        related_name="runs",
        verbose_name="Automação",
    )

    started_at = models.DateTimeField(default=timezone.now)  # 👈 aqui
    finished_at = models.DateTimeField("Fim", null=True, blank=True)

    status = models.CharField(
        "Status",
        max_length=20,
        choices=Status.choices,
        default=Status.RUNNING,
    )

    triggered_mode = models.CharField(
        "Modo de disparo",
        max_length=20,
        choices=TriggerMode.choices,
        default=TriggerMode.SCHEDULE,
    )

    triggered_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Usuário",
        help_text="Usuário que disparou manualmente (se aplicável).",
    )

    log = models.TextField(
        "Log de execução",
        blank=True,
        help_text="Saída de log (stdout/erros) capturada durante a execução.",
    )

    # 👇 NOVO: guarda o PID do processo externo
    external_pid = models.IntegerField(
        "PID do processo externo",
        null=True,
        blank=True,
        help_text="PID do processo da automação (para permitir cancelamento).",
    )

    created_at = models.DateTimeField("Registrado em", auto_now_add=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Execução de automação"
        verbose_name_plural = "Execuções de automação"

    def __str__(self) -> str:
        return f"{self.job.name} @ {self.started_at:%d/%m/%Y %H:%M}"
