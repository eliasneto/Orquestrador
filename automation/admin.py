# automation/admin.py
from django.contrib import admin
from .models import AutomationJob, AutomationRun


@admin.register(AutomationJob)
class AutomationJobAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "schedule_type",
        "one_off_run_at",
        "daily_time",
        "is_active",
        "allow_manual",
        "created_at",
    )
    list_filter = ("schedule_type", "is_active", "allow_manual")
    search_fields = ("name", "code", "description")

    fieldsets = (
        (
            "Dados básicos",
            {
                "fields": (
                    "name",
                    "description",
                    "code",
                    "external_main_script",
                )
            },
        ),
        (
            "Agendamento",
            {
                "fields": (
                    "schedule_type",
                    "one_off_run_at",   # 👈 aqui usamos o nome novo
                    "daily_time",
                )
            },
        ),
        (
            "Opções",
            {
                "fields": (
                    "is_active",
                    "allow_manual",
                )
            },
        ),
    )


@admin.register(AutomationRun)
class AutomationRunAdmin(admin.ModelAdmin):
    list_display = (
        "job",
        "started_at",
        "finished_at",
        "status",
        "triggered_mode",
        "triggered_by",
    )
    list_filter = ("status", "triggered_mode", "started_at")
    search_fields = ("job__name", "job__code", "triggered_by__username")
