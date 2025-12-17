# automation/permissions.py
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import user_passes_test  
from .models import AutomationJob, AutomationSectorPermission


def get_user_allowed_sectors(user):
    if not user.is_authenticated:
        return []

    if user.is_superuser or user.has_perm("automation.view_all_jobs"):
        return [choice[0] for choice in AutomationJob.Sector.choices]

    group_ids = list(user.groups.values_list("id", flat=True))
    if not group_ids:
        return []

    sectors = (
        AutomationSectorPermission.objects
        .filter(group_id__in=group_ids)
        .values_list("sector", flat=True)
        .distinct()
    )
    return list(sectors)


def get_job_for_user_or_404(user, pk):
    job = get_object_or_404(AutomationJob, pk=pk)
    allowed_sectors = get_user_allowed_sectors(user)

    if job.sector not in allowed_sectors:
        raise PermissionDenied("Você não tem acesso a esta automação.")

    return job


ORQ_ADMIN_GROUP = "administrador"


def is_orquestrador_admin(user) -> bool:
    if not user.is_authenticated:
        return False
    return user.is_superuser or user.groups.filter(name=ORQ_ADMIN_GROUP).exists()


class OrquestradorAdminRequiredMixin:
    def dispatch(self, request, *args, **kwargs):
        if not is_orquestrador_admin(request.user):
            raise PermissionDenied("Acesso restrito ao administrador do orquestrador.")
        return super().dispatch(request, *args, **kwargs)


def orquestrador_admin_required(view_func):
    return user_passes_test(is_orquestrador_admin)(view_func)
