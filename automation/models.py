# automation/models.py
"""
Modelos principais do módulo de automação.

Aqui definimos:
- AutomationJob: cadastro de cada automação (o “que” e “quando”).
- AutomationRun: histórico de execuções (o “quando rodou” e “como foi”).
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.conf import settings
from pathlib import Path
from django.db import models
from django.utils import timezone
User = get_user_model()
# automation/models.py
import datetime as dt
from datetime import timedelta
from django.utils.text import slugify
from django.contrib.auth.models import Group
# (provavelmente isso já está no topo; se não estiver, adicione)

# automation/models.py (apenas a classe AutomationJob)

class AutomationJob(models.Model):

    class ScheduleType(models.TextChoices):
        ONCE        = "once",        "Pontual"
        DAILY       = "daily",       "Diário"
        MULTI_DAILY = "multi_daily", "Diário – vários horários"
        INTERVAL    = "interval",    "A cada N minutos"

    # 🔹 NOVO: tipos de setor
    class Sector(models.TextChoices):
        GERAL = "geral", "Geral"
        FINANCEIRO = "financeiro", "Financeiro"
        COMERCIAL = "comercial", "Comercial"
        TI = "ti", "TI"
        JURIDICO = "juridico", "Jurídico"
        ADMINISTRADOR = "administrador", "Administrador"
        # "juridico" = valor salvo no banco (sem acento)
        # "Jurídico" = texto exibido no admin (com acento)     

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
        blank=True,  # 👈 permite vir vazio do form
        help_text="Identificador curto, sem espaços. Ex: robo_ixc_login_cliente",
    )

    # 🔹 setor da automação
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

    # 🔹 NOVO: pausa apenas o agendamento automático
    is_paused = models.BooleanField(
        "Agendamento pausado",
        default=False,
        help_text="Se verdadeiro, o scheduler não dispara esta automação automaticamente.",
    )
    ...
    # Agendamento
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

    # horário base para o diário (por exemplo todo dia às 10:30)
    daily_time = models.TimeField(
        "Horário diário",
        null=True,
        blank=True,
    )

    # 👉 NOVO: vários horários diários
    multi_daily_times = models.CharField(
        "Horários diários (lista)",
        max_length=200,
        blank=True,
        help_text="Horários HH:MM separados por vírgula. Ex.: 08:00, 13:00, 18:00",
    )

    # intervalo em minutos para o modo INTERVAL
    interval_minutes = models.PositiveIntegerField(
        "Intervalo (minutos)",
        null=True,
        blank=True,
        help_text="Usado quando o agendamento for 'a cada N minutos'.",
    )

    # próxima execução calculada pelo scheduler
    next_run_at = models.DateTimeField(
        "Próxima execução",
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    # ----------------- MULTI-DIÁRIO: parsing dos horários -----------------
    def get_multi_daily_times(self):
        """
        Converte o texto de multi_daily_times em lista de dt.time.
        Ignora valores inválidos.
        """
        times = []
        raw = (self.multi_daily_times or "").strip()
        if not raw:
            return []

        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                h, m = map(int, part.split(":"))
                times.append(dt.time(hour=h, minute=m))
            except ValueError:
                # horário inválido -> ignora
                continue

        # remove duplicados e ordena
        seen = set()
        uniq = []
        for t in times:
            if t not in seen:
                seen.add(t)
                uniq.append(t)
        return sorted(uniq)

    # ----------------- Cálculo da próxima execução -----------------
    def compute_next_run(self, from_dt=None):
        """Calcula a próxima execução a partir de uma data base."""
        now = from_dt or timezone.now()

        if not self.is_active:
            return None

        if self.schedule_type == self.ScheduleType.ONCE:
            # Pontual: em geral você usa one_off_run_at e depois zera
            return None

        if self.schedule_type == self.ScheduleType.INTERVAL:
            minutes = self.interval_minutes or 1
            return now + timedelta(minutes=minutes)

        if self.schedule_type == self.ScheduleType.DAILY:
            # Todo dia no horário escolhido
            if not self.daily_time:
                # se não tiver horário, assume agora + 1 dia
                return now + timedelta(days=1)

            base = timezone.make_aware(
                timezone.datetime.combine(now.date(), self.daily_time),
                timezone.get_current_timezone(),
            )

            if base > now:
                return base  # hoje ainda não passou

            # já passou hoje, agenda para amanhã nesse horário
            return base + timedelta(days=1)

        if self.schedule_type == self.ScheduleType.MULTI_DAILY:
            times = self.get_multi_daily_times()
            if not times:
                return None

            tz = timezone.get_current_timezone()
            today = now.date()

            # tenta achar ainda hoje o próximo horário
            for t in times:
                candidate = timezone.make_aware(
                    timezone.datetime.combine(today, t),
                    tz,
                )
                if candidate > now:
                    return candidate

            # se todos passaram hoje, pega o primeiro horário de amanhã
            tomorrow = today + timedelta(days=1)
            return timezone.make_aware(
                timezone.datetime.combine(tomorrow, times[0]),
                tz,
            )

        return None    

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
        return f"job_{self.pk or 'novo'}"

    # ---------- Descrição “bonita” do agendamento ----------
    @property
    def schedule_description(self) -> str:
        if self.schedule_type == self.ScheduleType.DAILY:
            if self.daily_time:
                return f"Diária às {self.daily_time.strftime('%H:%M')}"
            return "Diária (sem horário definido)"

        if self.schedule_type == self.ScheduleType.MULTI_DAILY:
            times = self.get_multi_daily_times()
            if not times:
                return "Diária em vários horários (nenhum definido)"
            lista = ", ".join(t.strftime("%H:%M") for t in times)
            return f"Diária nos horários: {lista}"

        if self.schedule_type == self.ScheduleType.INTERVAL:
            if self.interval_minutes:
                return f"A cada {self.interval_minutes} minuto(s)"
            return "A cada N minutos (intervalo não definido)"

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

        if self.schedule_type == self.ScheduleType.MULTI_DAILY:
            times = self.get_multi_daily_times()
            if not times:
                return "Horários não definidos"
            return ", ".join(t.strftime("%H:%M") for t in times)

        if self.schedule_type == self.ScheduleType.INTERVAL:
            if self.interval_minutes:
                return f"A cada {self.interval_minutes} min"
            return "Intervalo não definido"

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

    def is_due(self, now: dt.datetime) -> bool:
        # Ainda não usamos esse método no scheduler atual
        return False


    def _generate_code(self):
            """
            Gera um código único baseado no nome + data/hora.
            Ex.: 'blueez_medicao_0312250920'
            """
            base = slugify(self.name or "automacao")  # ex.: 'blueez-medicao'
            base = base.replace("-", "_")             # vira 'blueez_medicao'

            from django.utils import timezone
            timestamp = timezone.now().strftime("%d%m%y%H%M")  # 0312250920

            candidate = f"{base}_{timestamp}" if base else timestamp

            # garante que não passe de 100 chars
            max_len = self._meta.get_field("code").max_length
            if len(candidate) > max_len:
                candidate = candidate[:max_len]

            # se, por algum motivo, já existir, acrescenta sufixo _2, _3...
            original = candidate
            counter = 2
            Model = self.__class__
            while Model.objects.filter(code=candidate).exists():
                suffix = f"_{counter}"
                candidate = f"{original[: max_len - len(suffix)]}{suffix}"
                counter += 1

            return candidate

    def save(self, *args, **kwargs):
        # só gera código automaticamente na criação ou se estiver vazio
        if not self.code:
            self.code = self._generate_code()
        super().save(*args, **kwargs)


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


from django.db import models
from django.conf import settings
from django.utils import timezone

class AutomationEvent(models.Model):
    class EventType(models.TextChoices):
        SCHEDULE_TRIGGERED      = "schedule_triggered", "Agendamento disparado"
        SCHEDULE_SKIPPED_PAUSED = "schedule_skipped_paused", "Agendamento ignorado (pausado)"
        SCHEDULE_SKIPPED_INACTIVE = "schedule_skipped_inactive", "Agendamento ignorado (inativo)"
        MANUAL_START            = "manual_start", "Execução manual iniciada"
        MANUAL_STOP             = "manual_stop", "Execução manual interrompida"
        NEXT_RUN_UPDATED        = "next_run_updated", "Próxima execução atualizada"
        SCHEDULER_ERROR         = "scheduler_error", "Erro no scheduler"

    job = models.ForeignKey(
        "automation.AutomationJob",
        on_delete=models.CASCADE,
        related_name="events",
    )
    run = models.ForeignKey(
        "automation.AutomationRun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
        help_text="Execução relacionada (se houver).",
    )
    event_type = models.CharField(
        max_length=50,
        choices=EventType.choices,
    )
    message = models.TextField(blank=True)
    meta = models.JSONField(blank=True, null=True)  # detalhes extras (dict livre)

    created_at = models.DateTimeField(default=timezone.now)

    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Usuário que causou o evento (se aplicável).",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.created_at:%d/%m %H:%M}] {self.event_type} – {self.job.code}"



class AutomationSectorPermission(models.Model):
    """
    Liga um Grupo do Django a um ou mais 'setores' de automação.
    Ex.: Grupo 'Financeiro' -> setor 'financeiro'
    """
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="automation_sector_perms",
        verbose_name="Grupo",
    )
    sector = models.CharField(
        "Setor",
        max_length=50,
        choices=AutomationJob.Sector.choices,
    )

    class Meta:
        unique_together = ("group", "sector")
        verbose_name = "Permissão de setor de automação"
        verbose_name_plural = "Permissões de setor de automação"

    def __str__(self):
        return f"{self.group.name} → {self.get_sector_display()}"
