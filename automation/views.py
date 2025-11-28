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
    - GET: mostra arquivos que já estão na pasta
    - POST: recebe upload de arquivos e grava em automation_jobs/job_<id>/
    """

    template_name = "automation/job_files.html"

    def _get_job_and_files(self, pk):
        """
        Busca a automação e lista os arquivos da pasta dela.
        """
        job = get_object_or_404(AutomationJob, pk=pk)
        job_dir = job.get_job_dir()
        job_dir.mkdir(parents=True, exist_ok=True)

        files = []
        if job_dir.exists():
            for entry in sorted(job_dir.iterdir()):
                # não mostrar a .venv
                if entry.name == ".venv":
                    continue

                stat = entry.stat()
                files.append(
                    {
                        "name": entry.name,
                        "is_dir": entry.is_dir(),
                        "size": None if entry.is_dir() else stat.st_size,
                        "modified": timezone.datetime.fromtimestamp(
                            stat.st_mtime,
                            tz=timezone.get_current_timezone(),
                        ),
                    }
                )

        return job, job_dir, files

    def get(self, request, pk, *args, **kwargs):
        """
        Mostra o formulário de upload + lista de arquivos atuais.
        """
        job, job_dir, files = self._get_job_and_files(pk)
        form = JobFileUploadForm()
        context = {"job": job, "files": files, "form": form}
        return render(request, self.template_name, context)

    def post(self, request, pk, *args, **kwargs):
        """
        Recebe os arquivos enviados e grava na pasta do job.
        """
        job, job_dir, files = self._get_job_and_files(pk)
        form = JobFileUploadForm(request.POST, request.FILES)

        if form.is_valid():
            uploaded_files = form.cleaned_data["files"]  # <- já vem como lista

            if not uploaded_files:
                # Nenhum arquivo selecionado
                form.add_error("files", "Selecione pelo menos um arquivo.")
                context = {"job": job, "files": files, "form": form}
                return render(request, self.template_name, context)

            count = 0
            for f in uploaded_files:
                safe_name = Path(f.name).name  # evita paths malucos
                dest_path = job_dir / safe_name

                with dest_path.open("wb+") as dest:
                    for chunk in f.chunks():
                        dest.write(chunk)

                count += 1

            messages.success(
                request,
                f"{count} arquivo(s) enviado(s) para a pasta {job.workspace_folder_name}.",
            )
            return redirect("automation:job_files", pk=job.pk)

        # Form inválido → volta com erros
        context = {"job": job, "files": files, "form": form}
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
