# automation/views.py
"""
Views do módulo de automação.

Inclui:
- Lista de automações (jobs)
- Criação/edição de automação
- Lista de execuções
- Endpoint para disparo manual ("Executar agora")
- Tela de arquivos da automação (pasta + venv)
"""

# automation/views.py
from pathlib import Path
from django.utils import timezone
from django.contrib import messages
from django.views.generic import ListView, CreateView, UpdateView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.db.models import Count

from .forms import AutomationJobForm, JobFileUploadForm
from .models import AutomationJob, AutomationRun
from .services import execute_job_async



# =========================
#  Listagem e cadastro
# =========================

class AutomationJobListView(LoginRequiredMixin, ListView):
    """
    Lista todas as automações cadastradas.
    """

    model = AutomationJob
    template_name = "automation/job_list.html"
    context_object_name = "jobs"

    def get_queryset(self):
        # Anota o total de execuções por job (AutomationRun)
        return (
            AutomationJob.objects
            .annotate(runs_total=Count("runs"))
            .order_by("name")
        )


class AutomationJobCreateView(LoginRequiredMixin, CreateView):
    """
    Tela de criação de uma nova automação.
    """

    model = AutomationJob
    form_class = AutomationJobForm
    template_name = "automation/job_form.html"
    success_url = reverse_lazy("automation:job_list")

    def form_valid(self, form):
        messages.success(self.request, "Automação criada com sucesso.")
        return super().form_valid(form)


class AutomationJobUpdateView(LoginRequiredMixin, UpdateView):
    """
    Tela de edição de uma automação existente.
    """

    model = AutomationJob
    form_class = AutomationJobForm
    template_name = "automation/job_form.html"
    success_url = reverse_lazy("automation:job_list")

    def form_valid(self, form):
        messages.success(self.request, "Automação atualizada com sucesso.")
        return super().form_valid(form)


# =========================
#  Históricos de execução
# =========================

class AutomationRunListView(LoginRequiredMixin, ListView):
    """
    Lista de execuções recentes de todas as automações.
    """

    model = AutomationRun
    template_name = "automation/run_list.html"
    context_object_name = "runs"
    paginate_by = 20  # paginação simples


class AutomationJobRunListView(LoginRequiredMixin, ListView):
    """
    Lista de execuções de UMA automação específica.

    Usado quando o usuário clica no nome da automação na tela de jobs.
    """

    model = AutomationRun
    template_name = "automation/job_runs.html"
    context_object_name = "runs"
    paginate_by = 20

    def dispatch(self, request, *args, **kwargs):
        # Carregamos o job uma vez e guardamos em self.job
        self.job = get_object_or_404(AutomationJob, pk=self.kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        # Filtra execuções apenas desse job, mais recentes primeiro
        return (
            self.job.runs
            .select_related("triggered_by")
            .order_by("-started_at")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["job"] = self.job  # pra mostrar informações da automação no topo
        return ctx


# =========================
#  Upload de arquivos do Job
# =========================

class JobFilesView(LoginRequiredMixin, View):
    """
    Tela para gerenciar os arquivos de uma automação (pasta + venv).
    - GET: mostra arquivos que já estão na pasta (raiz ou subpasta)
    - POST: recebe upload de arquivos e grava na pasta atual
    """

    template_name = "automation/job_files.html"

    def _get_job_and_files(self, pk, subdir_param=None):
        """
        subdir_param = string tipo:
          - None ou ""        -> pasta raiz (job_X/)
          - "entrada"         -> job_X/entrada/
          - "entrada/logs"    -> job_X/entrada/logs/

        Garante que:
        - não haja path traversal
        - pasta atual exista
        - retorna lista de arquivos/pastas com info para o template
        """
        job = get_object_or_404(AutomationJob, pk=pk)

        base_dir = job.get_job_dir()  # já cria job_X/entrada/ e job_X/saida/
        base_dir.mkdir(parents=True, exist_ok=True)

        # normaliza a subpasta
        safe_subdir = (subdir_param or "").strip().strip("\\/")

        current_dir = base_dir
        if safe_subdir:
            candidate = base_dir / safe_subdir
            try:
                # garante que está dentro de base_dir
                candidate.relative_to(base_dir)
            except ValueError:
                # alguém tentou fazer coisa errada no querystring -> volta pra raiz
                safe_subdir = ""
                candidate = base_dir

            candidate.mkdir(parents=True, exist_ok=True)
            current_dir = candidate

        # string bonitinha para mostrar no header
        display_path = f"automation_jobs/job_{job.pk}/"
        if safe_subdir:
            display_path += safe_subdir + "/"

        files = []
        if current_dir.exists():
            for entry in sorted(current_dir.iterdir()):
                # não listamos a .venv
                if entry.name == ".venv":
                    continue

                stat = entry.stat()
                is_dir = entry.is_dir()

                # se for pasta, já preparamos qual subdir usar ao clicar
                subdir_for_child = None
                if is_dir:
                    subdir_for_child = (
                        f"{safe_subdir}/{entry.name}" if safe_subdir else entry.name
                    )

                files.append(
                    {
                        "name": entry.name,
                        "is_dir": is_dir,
                        "size": None if is_dir else stat.st_size,
                        "modified": timezone.datetime.fromtimestamp(
                            stat.st_mtime,
                            tz=timezone.get_current_timezone(),
                        ),
                        "subdir_param": subdir_for_child,
                    }
                )

        return job, base_dir, current_dir, display_path, files

    def get(self, request, pk):
        subdir = request.GET.get("subdir", "")
        job, base_dir, current_dir, display_path, files = self._get_job_and_files(
            pk, subdir
        )
        form = JobFileUploadForm()
        context = {
            "job": job,
            "files": files,
            "form": form,
            "current_path_display": display_path,
        }
        return render(request, self.template_name, context)

    def post(self, request, pk):
        subdir = request.GET.get("subdir", "")
        job, base_dir, current_dir, display_path, files = self._get_job_and_files(
            pk, subdir
        )
        form = JobFileUploadForm(request.POST, request.FILES)

        if form.is_valid():
            uploaded_files = request.FILES.getlist("files")
            count = 0

            for f in uploaded_files:
                # protege contra caminhos estranhos no nome
                safe_name = Path(f.name).name
                dest_path = current_dir / safe_name

                with dest_path.open("wb+") as dest:
                    for chunk in f.chunks():
                        dest.write(chunk)

                count += 1

            messages.success(
                request,
                f"{count} arquivo(s) enviado(s) para a pasta {display_path}.",
            )
            return redirect(f"{reverse_lazy('automation:job_files', kwargs={'pk': job.pk})}?subdir={subdir}")

        # Se o form for inválido, re-renderiza com erros
        context = {
            "job": job,
            "files": files,
            "form": form,
            "current_path_display": display_path,
        }
        return render(request, self.template_name, context)





# =========================
#  Disparo manual
# =========================

@require_POST
@login_required
def run_job_now(request, pk):
    """
    Dispara uma automação manualmente a partir do frontend.

    A execução é feita em background (thread), para não travar
    o navegador enquanto o script roda.
    """
    job = get_object_or_404(AutomationJob, pk=pk)

    if not job.allow_manual:
        messages.error(
            request, "Esta automação não permite disparo manual."
        )
        return redirect("automation:job_list")

    # Dispara em segundo plano
    execute_job_async(
        job,
        triggered_by=request.user,
        triggered_mode=AutomationRun.TriggerMode.MANUAL,
    )

    messages.success(
        request,
        f"Automação '{job.name}' enviada para execução em segundo plano. "
        "Atualize a página em alguns instantes para ver o status.",
    )

    return redirect("automation:job_list")
