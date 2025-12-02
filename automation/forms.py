# automation/forms.py
from datetime import timedelta

from django import forms
from django.utils import timezone

from .models import AutomationJob


class AutomationJobForm(forms.ModelForm):
    class Meta:
        model = AutomationJob
        fields = [
            "name",
            "description",
            "code",
            "sector",
            "external_main_script",
            "is_active",
            "allow_manual",
            "schedule_type",
            "one_off_run_at",      # 👈 pontual
            "daily_time",
            "multi_daily_times",   # 👈 horários múltiplos (08:00, 13:00, 18:00…)
            "interval_minutes",
            "next_run_at",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Ex: Robô IXC – Login Cliente"}
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Explique rapidamente o que essa automação faz.",
                }
            ),
            "sector": forms.Select(
                attrs={"class": "form-select"},
            ),
            "code": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "robo_ixc_login_cliente"}
            ),
            "external_main_script": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "main.py"}
            ),
            "schedule_type": forms.Select(attrs={"class": "form-select"}),
            "one_off_run_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"}
            ),
            "daily_time": forms.TimeInput(
                attrs={"class": "form-control", "type": "time"}
            ),
            "multi_daily_times": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ex.: 08:00, 13:00, 18:00",
                }
            ),
            "interval_minutes": forms.NumberInput(
                attrs={"class": "form-control", "min": "1"}
            ),
            "next_run_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"}
            ),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "allow_manual": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        f = self.fields

        if "schedule_type" in f:
            f["schedule_type"].label = "Tipo de agendamento"
            f["schedule_type"].help_text = (
                "Escolha se esta automação é pontual, diária ou recorrente a cada N minutos."
            )

        if "one_off_run_at" in f:
            f["one_off_run_at"].label = "Data/hora única (pontual)"
            f["one_off_run_at"].help_text = (
                "Usado quando o tipo de agendamento for 'pontual'. "
                "Define quando rodar uma única vez."
            )
            f["one_off_run_at"].required = False

        if "daily_time" in f:
            f["daily_time"].label = "Horário diário"
            f["daily_time"].help_text = (
                "Usado quando o agendamento for diário (ex.: 10:30)."
            )

        if "interval_minutes" in f:
            f["interval_minutes"].label = "Intervalo (minutos)"
            f["interval_minutes"].help_text = (
                "Usado quando o agendamento for 'a cada N minutos'."
            )

        if "next_run_at" in f:
            f["next_run_at"].label = "Próxima execução"
            f["next_run_at"].help_text = (
                "Momento em que o scheduler deve executar a próxima vez. "
                "É recalculado automaticamente após cada execução."
            )

        if "multi_daily_times" in f:
            f["multi_daily_times"].label = "Horários diários (lista)"
            f["multi_daily_times"].help_text = (
                "Informe horários HH:MM separados por vírgula. "
                "Ex.: 08:00, 13:00, 18:00"
            )
            f["multi_daily_times"].required = False

    def clean(self):
        cleaned = super().clean()
        schedule_type = cleaned.get("schedule_type")
        daily_time = cleaned.get("daily_time")
        interval_minutes = cleaned.get("interval_minutes")
        one_off_run_at = cleaned.get("one_off_run_at")

        # Diário → precisa de horário base
        if schedule_type == AutomationJob.ScheduleType.DAILY and not daily_time:
            self.add_error(
                "daily_time",
                "Informe o horário diário para este tipo de agendamento.",
            )

        # Intervalo → precisa de minutos >= 1
        if schedule_type == AutomationJob.ScheduleType.INTERVAL:
            if not interval_minutes:
                self.add_error(
                    "interval_minutes",
                    "Informe o intervalo em minutos.",
                )
            elif interval_minutes < 1:
                self.add_error(
                    "interval_minutes",
                    "O intervalo mínimo é de 1 minuto.",
                )

        # Pontual → se quiser obrigar uma data/hora, é aqui
        if schedule_type == AutomationJob.ScheduleType.ONCE:
            # if not one_off_run_at:
            #     self.add_error(
            #         "one_off_run_at",
            #         "Informe a data/hora para execução pontual.",
            #     )
            pass

        return cleaned

    def save(self, commit=True):
        """
        Ajusta next_run_at com base no tipo de agendamento:

        - once: next_run_at = one_off_run_at
        - daily: next_run_at = compute_next_run()
        - interval: next_run_at = agora + interval_minutes
        """
        instance: AutomationJob = super().save(commit=False)

        if not instance.is_active:
            instance.next_run_at = None
        else:
            now = timezone.now()

            if instance.schedule_type == AutomationJob.ScheduleType.INTERVAL:
                minutes = instance.interval_minutes or 1
                if instance.next_run_at is None:
                    instance.next_run_at = now + timedelta(minutes=minutes)

            elif instance.schedule_type == AutomationJob.ScheduleType.DAILY:
                instance.next_run_at = instance.compute_next_run(from_dt=now)

            elif instance.schedule_type == AutomationJob.ScheduleType.ONCE:
                if instance.one_off_run_at:
                    instance.next_run_at = instance.one_off_run_at

        if commit:
            instance.save()
            self.save_m2m()

        return instance


# ---------- Upload múltiplo de arquivos (para a tela de arquivos do job) ----------

class MultiFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultiFileField(forms.Field):
    """
    Campo simples que recebe uma LISTA de arquivos.

    Não usa FileField justamente pra não dar o erro
    "No file was submitted..." quando vier uma lista.
    """

    widget = MultiFileInput

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("required", False)
        super().__init__(*args, **kwargs)

    def to_python(self, data):
        if not data:
            return []
        return data


class JobFileUploadForm(forms.Form):
    files = MultiFileField(
        label="Selecione um ou mais arquivos",
        widget=MultiFileInput(
            attrs={
                "class": "form-control",
            }
        ),
    )
