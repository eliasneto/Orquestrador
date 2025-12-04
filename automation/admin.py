# automation/admin.py
from django.contrib import admin

from .models import (
    AutomationJob,
    AutomationRun,
    AutomationEvent,
    AutomationSectorPermission,
)


@admin.register(AutomationJob)
class AutomationJobAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "sector",
        "schedule_type",
        "is_active",
        "allow_manual",
        "is_paused",
        "next_run_at",
        "created_at",
    )
    list_filter = ("sector", "schedule_type", "is_active", "allow_manual", "is_paused")
    search_fields = ("name", "code", "description")
    ordering = ("name",)


@admin.register(AutomationRun)
class AutomationRunAdmin(admin.ModelAdmin):
    """
    Histórico de execuções.
    Aqui NÃO existe campo 'group' nem 'sector' direto.
    O setor vem do job (job.sector), então usamos um método helper.
    """

    list_display = (
        "job",
        "get_sector",
        "status",
        "triggered_mode",
        "triggered_by",
        "started_at",
        "finished_at",
    )
    list_filter = (
        "status",
        "triggered_mode",
        "job__sector",
    )
    search_fields = (
        "job__name",
        "job__code",
        "triggered_by__username",
    )
    date_hierarchy = "started_at"

    def get_sector(self, obj):
        return obj.job.get_sector_display()
    get_sector.short_description = "Setor"
    get_sector.admin_order_field = "job__sector"


@admin.register(AutomationEvent)
class AutomationEventAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "job",
        "get_sector",
        "event_type",
        "run",
        "triggered_by",
    )
    list_filter = ("event_type", "job__sector")
    search_fields = (
        "job__name",
        "job__code",
        "message",
        "triggered_by__username",
    )
    date_hierarchy = "created_at"

    def get_sector(self, obj):
        return obj.job.get_sector_display()
    get_sector.short_description = "Setor"
    get_sector.admin_order_field = "job__sector"


@admin.register(AutomationSectorPermission)
class AutomationSectorPermissionAdmin(admin.ModelAdmin):
    """
    Mapeia Grupo ↔ Setor de automação.
    Ex.: Grupo 'Financeiro' -> setor 'financeiro'
    """

    list_display = ("group", "sector")
    list_filter = ("sector", "group")
    search_fields = ("group__name",)
