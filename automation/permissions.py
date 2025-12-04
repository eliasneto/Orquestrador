# automation/permissions.py
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from .models import AutomationJob, AutomationSectorPermission


def get_user_allowed_sectors(user):
    """
    Retorna uma lista de setores (values do ChoiceField) que o usuário pode ver.
    A regra agora é:
      - superuser ou quem tem permissão 'automation.view_all_jobs' vê TUDO
      - demais usuários só veem setores configurados em AutomationSectorPermission
      - se não tiver permissão nenhuma configurada -> não vê nada
    """
    if not user.is_authenticated:
        return []

    # superuser ou permissão especial -> vê todos os setores
    if user.is_superuser or user.has_perm("automation.view_all_jobs"):
        return [choice[0] for choice in AutomationJob.Sector.choices]

    # pega IDs dos grupos do usuário
    group_ids = list(user.groups.values_list("id", flat=True))
    if not group_ids:
        # sem grupo => sem setor
        return []

    # busca permissões configuradas para esses grupos
    sectors = (
        AutomationSectorPermission.objects
        .filter(group_id__in=group_ids)
        .values_list("sector", flat=True)
        .distinct()
    )

    return list(sectors)


def get_job_for_user_or_404(user, pk):
    """
    Busca um job e garante que o usuário tenha permissão pelo setor.
    """
    job = get_object_or_404(AutomationJob, pk=pk)
    allowed_sectors = get_user_allowed_sectors(user)

    if job.sector not in allowed_sectors:
        raise PermissionDenied("Você não tem acesso a esta automação.")

    return job
