# automation/views.py
"""
Views do módulo de automação.

Inclui:
- Lista de automações (jobs)
- Criação/edição/pausa/retomada de automação
- Lista de execuções e detalhes
- Logs de eventos do orquestrador
- Endpoint para disparo/parada manual ("Executar agora" / "Parar")
- Tela de arquivos da automação (pasta + venv)
- Reset do workspace do job
"""

from __future__ import annotations

import os
import signal
import shutil
from pathlib import Path
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Max
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, UpdateView, View

from accounts.permissions import AdminRequiredMixin
from .forms import AutomationJobForm, JobFileUploadForm
from .models import AutomationEvent, AutomationJob, AutomationRun
from .permissions import (
    OrquestradorAdminRequiredMixin,
    orquestrador_admin_required,
    is_orquestrador_admin,
    get_job_for_user_or_404,
    get_user_allowed_sectors,
)
from .services import execute_job_async, log_automation_event


# ============================================================================
# Helpers de EventType (fallback não quebra se não existir no Enum)
# ============================================================================

def _evt(name: str, fallback: str) -> str:
    return getattr(AutomationEvent.EventType, name, fallback)


EVT_PAUSED = _evt("PAUSED", "paused")
EVT_RESUMED = _evt("RESUMED", "resumed")
EVT_WORKSPACE_RESET = _evt("WORKSPACE_RESET", "workspace_reset")
EVT_VENV_RESET = _evt("VENV_RESET", "venv_reset")
EVT_FOLDER_RESET = _evt("FOLDER_RESET", "folder_reset")


# ============================================================================
# Helpers de filesystem
# ============================================================================

def _safe_delete_path(p: Path) -> None:
    """Remove arquivo/pasta/link de forma segura."""
    try:
        if p.is_symlink():
            p.unlink()
        elif p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        else:
            p.unlink()
    except FileNotFoundError:
        pass


def _clear_dir_contents(dir_path: Path) -> int:
    """Apaga tudo dentro da pasta, mantendo a pasta."""
    removed = 0
    if not dir_path.exists() or not dir_path.is_dir():
        return 0

    for child in dir_path.iterdir():
        _safe_delete_path(child)
        removed += 1

    return removed


# ============================================================================
# Pausar / retomar agendamento (ADMIN + grupo administrador_Orquestrador)
# ============================================================================

class AutomationJobPauseView(LoginRequiredMixin, OrquestradorAdminRequiredMixin, View):
    def post(self, request, pk):
        job = get_job_for_user_or_404(request.user, pk)

        job.is_paused = True
        job.next_run_at = None
        job.save(update_fields=["is_paused", "next_run_at"])

        try:
            log_automation_event(job, EVT_PAUSED, user=request.user, message="Agendamento pausado via interface.")
        except Exception:
            pass

        messages.info(request, f"Agendamento da automação '{job.name}' foi pausado.")
        return redirect("automation:job_list")


class AutomationJobResumeView(LoginRequiredMixin, OrquestradorAdminRequiredMixin, View):
    def post(self, request, pk):
        job = get_job_for_user_or_404(request.user, pk)

        job.is_paused = False
        if job.is_active:
            job.next_run_at = job.compute_next_run(from_dt=timezone.now())
        job.save(update_fields=["is_paused", "next_run_at"])

        try:
            log_automation_event(job, EVT_RESUMED, user=request.user, message="Agendamento retomado via interface.")
        except Exception:
            pass

        messages.success(request, f"Agendamento da automação '{job.name}' foi retomado.")
        return redirect("automation:job_list")


# ============================================================================
# Listagem e cadastro
# - LISTA: qualquer usuário com acesso ao setor
# - CREATE/UPDATE/DELETE: Admin + grupo administrador_Orquestrador
# ============================================================================

class AutomationJobListView(LoginRequiredMixin, ListView):
    model = AutomationJob
    template_name = "automation/job_list.html"
    context_object_name = "jobs"

    def get_queryset(self):
        allowed_sectors = get_user_allowed_sectors(self.request.user)
        return (
            AutomationJob.objects
            .filter(sector__in=allowed_sectors)
            .annotate(runs_total=Count("runs"), last_run_at=Max("runs__started_at"))
            .order_by("name")
        )


class AutomationJobCreateView(LoginRequiredMixin, OrquestradorAdminRequiredMixin, CreateView):
    model = AutomationJob
    form_class = AutomationJobForm
    template_name = "automation/job_form.html"
    success_url = reverse_lazy("automation:job_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Automação criada com sucesso.")
        return super().form_valid(form)

    


class AutomationJobUpdateView(LoginRequiredMixin, OrquestradorAdminRequiredMixin, UpdateView):
    model = AutomationJob
    form_class = AutomationJobForm
    template_name = "automation/job_form.html"
    success_url = reverse_lazy("automation:job_list")

    def get_queryset(self):
        allowed = get_user_allowed_sectors(self.request.user)
        return AutomationJob.objects.filter(sector__in=allowed)

    def form_valid(self, form):
        messages.success(self.request, "Automação atualizada com sucesso.")
        return super().form_valid(form)


class AutomationJobDeleteView(LoginRequiredMixin, OrquestradorAdminRequiredMixin, DeleteView):
    model = AutomationJob
    template_name = "automation/job_confirm_delete.html"
    success_url = reverse_lazy("automation:job_list")

    def get_queryset(self):
        allowed = get_user_allowed_sectors(self.request.user)
        return AutomationJob.objects.filter(sector__in=allowed)


# ============================================================================
# Históricos de execução
# - Lista geral de runs: qualquer usuário com acesso ao setor (sem admin)
# - Runs de um job: idem
# ============================================================================

class AutomationRunListView(LoginRequiredMixin, ListView):
    model = AutomationRun
    template_name = "automation/run_list.html"
    context_object_name = "runs"
    paginate_by = 20

    def get_queryset(self):
        allowed_sectors = get_user_allowed_sectors(self.request.user)
        return (
            AutomationRun.objects
            .select_related("job", "triggered_by")
            .filter(job__sector__in=allowed_sectors)
            .order_by("-started_at")
        )


class AutomationJobRunListView(LoginRequiredMixin, ListView):
    model = AutomationRun
    template_name = "automation/job_runs.html"
    context_object_name = "runs"
    paginate_by = 20

    def dispatch(self, request, *args, **kwargs):
        self.job = get_job_for_user_or_404(request.user, self.kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return self.job.runs.select_related("triggered_by").order_by("-started_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["job"] = self.job
        return ctx


class AutomationEventListView(LoginRequiredMixin, OrquestradorAdminRequiredMixin, ListView):
    
    model = AutomationEvent
    template_name = "automation/event_list.html"
    context_object_name = "events"
    paginate_by = 50

    def get_queryset(self):
        allowed_sectors = get_user_allowed_sectors(self.request.user)
        if not allowed_sectors:
            return AutomationEvent.objects.none()

        qs = (
            AutomationEvent.objects
            .select_related("job", "run", "triggered_by")
            .filter(job__sector__in=allowed_sectors)
            .order_by("-created_at")
        )

        job_id = self.request.GET.get("job")
        if job_id:
            qs = qs.filter(job_id=job_id)

        event_type = self.request.GET.get("type")
        if event_type:
            qs = qs.filter(event_type=event_type)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        allowed_sectors = get_user_allowed_sectors(self.request.user)
        ctx["jobs"] = AutomationJob.objects.filter(sector__in=allowed_sectors).order_by("name")
        ctx["selected_job"] = self.request.GET.get("job") or ""
        ctx["selected_type"] = self.request.GET.get("type") or ""
        ctx["event_types"] = AutomationEvent.EventType.choices
        return ctx


# ============================================================================
# Upload/Lista de arquivos do Job
# ============================================================================

class JobFilesView(LoginRequiredMixin, View):
    template_name = "automation/job_files.html"

    def _get_job_and_files(self, user, pk, subdir_param=None):
        job = get_job_for_user_or_404(user, pk)

        base_dir = job.get_job_dir()
        base_dir.mkdir(parents=True, exist_ok=True)

        safe_subdir = (subdir_param or "").strip().strip("\\/")

        current_dir = base_dir
        if safe_subdir:
            candidate = base_dir / safe_subdir
            try:
                candidate.relative_to(base_dir)
            except ValueError:
                safe_subdir = ""
                candidate = base_dir

            candidate.mkdir(parents=True, exist_ok=True)
            current_dir = candidate

        display_path = f"automation_jobs/job_{job.pk}/" + (safe_subdir + "/" if safe_subdir else "")

        ALLOWED_DOWNLOAD_ROOTS = ("entrada", "saida")
        first_segment = safe_subdir.split("/", 1)[0] if safe_subdir else None

        files = []
        if current_dir.exists():
            for entry in sorted(current_dir.iterdir()):
                if entry.name == ".venv":
                    continue

                stat = entry.stat()
                is_dir = entry.is_dir()

                subdir_for_child = None
                if is_dir:
                    subdir_for_child = f"{safe_subdir}/{entry.name}" if safe_subdir else entry.name

                can_download = (not is_dir) and (first_segment in ALLOWED_DOWNLOAD_ROOTS)

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
                        "can_download": can_download,
                    }
                )

        return job, base_dir, current_dir, display_path, files

    def get(self, request, pk):
        subdir = request.GET.get("subdir", "")
        job, _base_dir, _current_dir, display_path, files = self._get_job_and_files(request.user, pk, subdir)
        form = JobFileUploadForm()
        return render(
            request,
            self.template_name,
            {
                "job": job,
                "files": files,
                "form": form,
                "current_path_display": display_path,
                "current_subdir": subdir,
                "is_orq_admin": is_orquestrador_admin(request.user),
            },
        )

    def post(self, request, pk):
        subdir = request.GET.get("subdir", "")
        job, _base_dir, current_dir, display_path, files = self._get_job_and_files(request.user, pk, subdir)
        form = JobFileUploadForm(request.POST, request.FILES)

        if form.is_valid():
            uploaded_files = request.FILES.getlist("files")
            count = 0

            for f in uploaded_files:
                safe_name = Path(f.name).name
                dest_path = current_dir / safe_name

                with dest_path.open("wb+") as dest:
                    for chunk in f.chunks():
                        dest.write(chunk)

                count += 1

            messages.success(request, f"{count} arquivo(s) enviado(s) para a pasta {display_path}.")
            url = reverse_lazy("automation:job_files", kwargs={"pk": job.pk})
            return redirect(f"{url}?subdir={quote(subdir, safe='/')}" if subdir else url)

        return render(
            request,
            self.template_name,
            {
                "job": job,
                "files": files,
                "form": form,
                "current_path_display": display_path,
                "current_subdir": subdir,
                "is_orq_admin": is_orquestrador_admin(request.user),
            },
        )


class JobFileDownloadView(LoginRequiredMixin, View):
    ALLOWED_DOWNLOAD_ROOTS = ("entrada", "saida")

    def get(self, request, pk):
        job = get_job_for_user_or_404(request.user, pk)
        base_dir = job.get_job_dir()

        subdir = (request.GET.get("subdir") or "").strip().strip("\\/")
        filename = request.GET.get("name")
        if not filename:
            raise Http404("Arquivo não especificado.")

        filename_safe = Path(filename).name

        current_dir = base_dir
        if subdir:
            candidate_dir = base_dir / subdir
            try:
                candidate_dir.relative_to(base_dir)
            except ValueError:
                raise Http404("Caminho inválido.")
            current_dir = candidate_dir

        file_path = current_dir / filename_safe
        if not file_path.exists() or not file_path.is_file():
            raise Http404("Arquivo não encontrado.")

        try:
            rel_path = file_path.relative_to(base_dir)
        except ValueError:
            raise Http404("Arquivo fora da pasta do job.")

        first_segment = rel_path.parts[0] if rel_path.parts else None
        if first_segment not in self.ALLOWED_DOWNLOAD_ROOTS:
            raise Http404("Download não permitido para este arquivo.")

        return FileResponse(open(file_path, "rb"), as_attachment=True, filename=filename_safe)


# ============================================================================
# Disparo manual / parada
# ============================================================================
@require_POST
@login_required
def run_job_now(request, pk):
    job = get_job_for_user_or_404(request.user, pk)

    if not job.is_active:
        messages.error(request, "Esta automação está inativa. Ative-a antes de executar manualmente.")
        return redirect("automation:job_list")

    if not job.allow_manual:
        messages.error(request, "Esta automação não permite disparo manual.")
        return redirect("automation:job_list")

    if AutomationRun.objects.filter(job=job, status=AutomationRun.Status.RUNNING).exists():
        messages.warning(request, "Esta automação já está em execução. Aguarde a conclusão.")
        return redirect("automation:job_list")

    try:
        log_automation_event(
            job,
            AutomationEvent.EventType.MANUAL_START,
            user=request.user,
            message="Execução manual disparada via interface (run_job_now).",
        )
    except Exception:
        pass

    execute_job_async(job, triggered_by=request.user, triggered_mode=AutomationRun.TriggerMode.MANUAL)

    messages.success(
        request,
        f"Automação '{job.name}' enviada para execução em segundo plano. "
        "Atualize a página em alguns instantes para ver o status.",
    )
    return redirect("automation:job_list")


@require_POST
@login_required
def stop_job(request, pk):
    job = get_job_for_user_or_404(request.user, pk)

    run = AutomationRun.objects.filter(job=job, status=AutomationRun.Status.RUNNING).first()
    if not run:
        messages.warning(request, "Nenhuma execução em andamento para esta automação.")
        return redirect("automation:job_list")

    if not run.external_pid:
        messages.error(request, "PID do processo não está registrado; não foi possível solicitar parada.")
        return redirect("automation:job_list")

    try:
        os.kill(run.external_pid, signal.SIGTERM)

        now = timezone.now()
        extra_log = (
            f"\n[{now.isoformat()}] ❌ Execução interrompida manualmente pelo usuário "
            f"{request.user.username}.\n"
        )

        run.log = (run.log or "") + extra_log
        run.status = AutomationRun.Status.FAILED
        run.finished_at = now
        run.save(update_fields=["log", "status", "finished_at"])

        try:
            log_automation_event(
                job,
                AutomationEvent.EventType.MANUAL_STOP,
                run=run,
                user=request.user,
                message="Execução interrompida manualmente via interface (stop_job).",
                meta={"pid": run.external_pid},
            )
        except Exception:
            pass

        messages.success(request, "Parada da automação solicitada com sucesso.")

    except ProcessLookupError:
        messages.warning(request, "O processo já não estava mais em execução (finalizou antes).")
        try:
            log_automation_event(
                job,
                AutomationEvent.EventType.MANUAL_STOP,
                run=run,
                user=request.user,
                message="Tentativa de parada manual, mas o processo já havia finalizado (ProcessLookupError).",
                meta={"pid": run.external_pid},
            )
        except Exception:
            pass

    except Exception as e:
        messages.error(request, f"Falha ao solicitar parada: {e}")

    return redirect("automation:job_list")


@login_required
def api_run_log(request, pk):
    run = get_object_or_404(AutomationRun.objects.select_related("job"), pk=pk)

    allowed = get_user_allowed_sectors(request.user)
    if run.job.sector not in allowed:
        raise Http404()

    return JsonResponse(
        {
            "id": run.id,
            "status": run.status,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "log": run.log or "",
        }
    )


# ============================================================================
# Reset do WORKSPACE / VENV / FOLDER (somente grupo administrador_Orquestrador)
# ============================================================================

@require_POST
@login_required
@orquestrador_admin_required
def job_reset_workspace(request, pk):
    job = get_job_for_user_or_404(request.user, pk)

    if job.runs.filter(status=AutomationRun.Status.RUNNING).exists():
        messages.error(request, "Não posso resetar a pasta enquanto o job está em execução.")
        return redirect("automation:job_files", pk=job.pk)

    job_dir = Path(job.get_job_dir())
    keep_dirs = {"entrada", "saida"}

    removed = 0
    errors = 0

    for item in job_dir.iterdir():
        if item.is_dir() and item.name in keep_dirs:
            try:
                removed += _clear_dir_contents(item)
            except Exception:
                errors += 1
            continue

        try:
            _safe_delete_path(item)
            removed += 1
        except Exception:
            errors += 1

    try:
        log_automation_event(
            job,
            EVT_WORKSPACE_RESET,
            user=request.user,
            message="Reset completo do workspace (mantém entrada/saida, limpa conteúdo).",
            meta={"removed": removed, "errors": errors},
        )
    except Exception:
        pass

    if errors == 0:
        messages.success(request, f"✅ Reset completo: removi {removed} item(ns). Mantive entrada/ e saida/ (conteúdo limpo).")
    else:
        messages.warning(request, f"⚠️ Reset parcial: removi {removed} item(ns), mas {errors} falharam ao remover.")

    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER")
    return redirect(next_url or reverse_lazy("automation:job_files", kwargs={"pk": job.pk}))


@require_POST
@login_required
@orquestrador_admin_required
def job_reset_venv(request, pk: int):
    job = get_job_for_user_or_404(request.user, pk)

    if AutomationRun.objects.filter(job=job, status=AutomationRun.Status.RUNNING).exists():
        messages.error(request, "Não posso resetar a venv enquanto o job está em execução.")
        return redirect("automation:job_files", pk=job.pk)

    venv_dir = Path(job.get_job_dir()) / ".venv"

    if venv_dir.exists():
        shutil.rmtree(venv_dir, ignore_errors=True)

        try:
            log_automation_event(
                job,
                EVT_VENV_RESET,
                user=request.user,
                message="Venv removida pelo usuário (reset).",
                meta={"path": str(venv_dir)},
            )
        except Exception:
            pass

        messages.success(request, "Venv removida. Na próxima execução ela será recriada.")
    else:
        messages.info(request, "Esse job não tem venv ainda (nada para remover).")

    return redirect("automation:job_files", pk=job.pk)


@require_POST
@login_required
@orquestrador_admin_required
def job_reset_folder(request, pk: int):
    job = get_job_for_user_or_404(request.user, pk)

    if AutomationRun.objects.filter(job=job, status=AutomationRun.Status.RUNNING).exists():
        messages.error(request, "Não posso resetar a pasta enquanto a automação estiver em execução.")
        return redirect("automation:job_files", pk=job.pk)

    job_dir = Path(job.get_job_dir())
    keep_dirs = {"entrada", "saida"}

    removed = 0
    errors = 0

    for item in job_dir.iterdir():
        if item.is_dir() and item.name in keep_dirs:
            continue

        try:
            _safe_delete_path(item)
            removed += 1
        except Exception:
            errors += 1

    try:
        log_automation_event(
            job,
            EVT_FOLDER_RESET,
            user=request.user,
            message="Reset da pasta do job (mantém entrada/saida).",
            meta={"removed": removed, "errors": errors},
        )
    except Exception:
        pass

    if errors == 0:
        messages.success(request, f"✅ Reset concluído: removi {removed} item(ns). Mantive entrada/ e saida/.")
    else:
        messages.warning(request, f"⚠️ Reset parcial: removi {removed} item(ns), mas {errors} falharam ao remover.")

    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER")
    return redirect(next_url or reverse_lazy("automation:job_files", kwargs={"pk": job.pk}))
