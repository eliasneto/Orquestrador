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
from django.db.models import Count, Q, Max
import os
import signal 
from .forms import AutomationJobForm, JobFileUploadForm
from .models import AutomationJob, AutomationRun
from .services import execute_job_async



# =========================
#  Listagem e cadastro
# =========================

# automation/views.py

class AutomationJobListView(LoginRequiredMixin, ListView):
    """
    Lista todas as automações cadastradas.
    """
    model = AutomationJob
    template_name = "automation/job_list.html"
    context_object_name = "jobs"

    def get_queryset(self):
        return (
            AutomationJob.objects
            .annotate(
                runs_total=Count("runs"),
                last_run_at=Max("runs__started_at"),   # para colocar o horario de inicio na lista de automações na coluna execusão
                #last_run_at = Max("runs__finished_at") para colocar o horario do termino na lista de automações na coluna execusão

            )
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

        # 🔹 NOVO: raiz "permitida" para download
        ALLOWED_DOWNLOAD_ROOTS = ("entrada", "saida")        

        # qual a primeira pasta (top-level) desse subdir?
        first_segment = None
        if safe_subdir:
            first_segment = safe_subdir.split("/", 1)[0]

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

        
                # 🔹 só deixa download se:
                # - NÃO for diretório
                # - estivermos dentro de 'entrada' ou 'saida'
                can_download = False
                if (not is_dir) and first_segment in ALLOWED_DOWNLOAD_ROOTS:
                    can_download = True

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
                        "can_download": can_download,   # 👈 NOVO
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
            "current_subdir": subdir,   # 👈 para montar link de download
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
            "current_subdir": subdir,   # 👈 idem
        }
        return render(request, self.template_name, context)


from django.http import FileResponse, Http404
...

class JobFileDownloadView(LoginRequiredMixin, View):
    """
    Faz download de um arquivo de 'entrada' ou 'saida' de uma automação.
    Não permite baixar arquivos de outras pastas (scripts, etc).
    """

    ALLOWED_DOWNLOAD_ROOTS = ("entrada", "saida")

    def get(self, request, pk):
        job = get_object_or_404(AutomationJob, pk=pk)
        base_dir = job.get_job_dir()

        subdir = (request.GET.get("subdir") or "").strip().strip("\\/")
        filename = request.GET.get("name")

        if not filename:
            raise Http404("Arquivo não especificado.")

        # garante nome "seguro" (sem path traversal via nome)
        filename_safe = Path(filename).name

        # monta diretório alvo a partir do subdir, com proteção
        current_dir = base_dir
        if subdir:
            candidate_dir = base_dir / subdir
            try:
                candidate_dir.relative_to(base_dir)
            except ValueError:
                # tentativa de escapar da pasta base
                raise Http404("Caminho inválido.")

            current_dir = candidate_dir

        file_path = current_dir / filename_safe

        # valida se o arquivo existe
        if not file_path.exists() or not file_path.is_file():
            raise Http404("Arquivo não encontrado.")

        # 🔒 GARANTIA: arquivo precisa estar dentro de 'entrada' ou 'saida'
        try:
            rel_path = file_path.relative_to(base_dir)
        except ValueError:
            raise Http404("Arquivo fora da pasta do job.")

        first_segment = rel_path.parts[0] if rel_path.parts else None
        if first_segment not in self.ALLOWED_DOWNLOAD_ROOTS:
            # Nada fora de entrada/saida pode ser baixado
            raise Http404("Download não permitido para este arquivo.")

        # Tudo ok, devolve como FileResponse
        return FileResponse(
            open(file_path, "rb"),
            as_attachment=True,
            filename=filename_safe,
        )



# =========================
#  Disparo manual
# =========================

@require_POST
@login_required
def run_job_now(request, pk):
    ...
    job = get_object_or_404(AutomationJob, pk=pk)


    # 🚫 NOVO: não deixa rodar se estiver inativa
    if not job.is_active:
        messages.error(
            request,
            "Esta automação está inativa. Ative-a antes de executar manualmente."
        )
        return redirect("automation:job_list")

    if not job.allow_manual:
        messages.error(request, "Esta automação não permite disparo manual.")
        return redirect("automation:job_list")

    # 🚫 impede execução concorrente
    if AutomationRun.objects.filter(
        job=job,
        status=AutomationRun.Status.RUNNING,
    ).exists():
        messages.warning(
            request,
            "Esta automação já está em execução. Aguarde a conclusão antes de disparar novamente.",
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


@require_POST
@login_required
@require_POST
@login_required
def stop_job(request, pk):
    job = get_object_or_404(AutomationJob, pk=pk)

    # Procura uma execução em andamento desse job
    run = AutomationRun.objects.filter(
        job=job,
        status=AutomationRun.Status.RUNNING,
    ).first()

    if not run:
        messages.warning(
            request,
            "Nenhuma execução em andamento para esta automação."
        )
        return redirect("automation:job_list")

    if not run.external_pid:
        messages.error(
            request,
            "PID do processo não está registrado; não foi possível solicitar parada."
        )
        return redirect("automation:job_list")

    try:
        # Tenta matar o processo
        os.kill(run.external_pid, signal.SIGTERM)

        # Marca no log e atualiza status
        now = timezone.now()
        extra_log = (
            f"\n[{now.isoformat()}] ❌ Execução interrompida manualmente pelo usuário "
            f"{request.user.username}.\n"
        )

        run.log = (run.log or "") + extra_log
        run.status = AutomationRun.Status.FAILED
        run.finished_at = now
        run.save(update_fields=["log", "status", "finished_at"])

        messages.success(request, "Parada da automação solicitada com sucesso.")
    except ProcessLookupError:
        # Processo já tinha morrido
        messages.warning(
            request,
            "O processo já não estava mais em execução (foi finalizado antes)."
        )

    return redirect("automation:job_list")

