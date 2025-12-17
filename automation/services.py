# automation/services.py
"""
Serviços de execução de automações.

Modelo: **pasta + venv por job**

Fluxo:
- Cada AutomationJob tem uma pasta: BASE/automation_jobs/job_<id>/
- Dentro dela ficam:
    - requirements.txt  (opcional)
    - main.py (ou outro nome definido em external_main_script)
    - quaisquer arquivos da automação

Execução:
1) Garante pasta do job
2) Garante .venv dentro da pasta (cria se não existir)
3) Se existir requirements.txt, instala/atualiza libs no venv
4) Executa o script principal usando python do venv
5) Salva log (stdout/stderr) no campo log de AutomationRun (com live update)
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from .models import AutomationEvent, AutomationJob, AutomationRun

# ==========================
#  Caminhos básicos
# ==========================

AUTOMATION_ROOT = Path(settings.BASE_DIR) / "automation_jobs"
AUTOMATION_ROOT.mkdir(parents=True, exist_ok=True)


# ==========================
#  Logger "ao vivo" (DB)
# ==========================

class LiveRunLogger:
    """
    Buffer que acumula em memória e também grava periodicamente em run.log no banco,
    para o front mostrar o log "em tempo real".
    """
    def __init__(self, run: AutomationRun, flush_interval: float = 1.0, max_chars: int = 200_000):
        self.run = run
        self.flush_interval = flush_interval
        self.max_chars = max_chars
        self._buf = io.StringIO()
        self._last_flush = 0.0

    def write(self, text: str):
        if not text:
            return
        self._buf.write(text)
        now = time.monotonic()
        if now - self._last_flush >= self.flush_interval:
            self.flush()

    def flush(self):
        val = self._buf.getvalue()

        # evita crescer infinito no banco
        if self.max_chars and len(val) > self.max_chars:
            val = val[-self.max_chars:]
            self._buf = io.StringIO()
            self._buf.write(val)

        self.run.log = val
        self.run.save(update_fields=["log"])
        self._last_flush = time.monotonic()

    def getvalue(self) -> str:
        return self._buf.getvalue()


def _log(buffer, msg: str):
    """Log compatível com LiveRunLogger / StringIO / arquivo / list."""
    if msg is None:
        return
    if not msg.endswith("\n"):
        msg += "\n"

    if hasattr(buffer, "write"):
        buffer.write(msg)
        return

    if isinstance(buffer, list):
        buffer.append(msg)
        return

    print(msg, end="")


# ==========================
#  Scheduler (jobs pendentes)
# ==========================

def run_pending_jobs():
    """
    Dispara automaticamente os jobs agendados cujo next_run_at já passou.
    Deve ser chamada periodicamente (ex.: a cada 1 minuto).

    Também registra evento quando job está pausado e a execução é pulada.
    """
    now = timezone.now()

    jobs_to_run = (
        AutomationJob.objects.filter(is_active=True, is_paused=False)
        .exclude(next_run_at__isnull=True)
        .filter(next_run_at__lte=now)
    )

    paused_jobs = (
        AutomationJob.objects.filter(is_active=True, is_paused=True)
        .exclude(next_run_at__isnull=True)
        .filter(next_run_at__lte=now)
    )

    # loga os pausados como “consumidos”
    for job in paused_jobs:
        log_automation_event(
            job,
            AutomationEvent.EventType.SCHEDULE_SKIPPED_PAUSED,
            message=(
                f"Execução programada para {job.next_run_at} "
                f"ignorada porque a automação está pausada."
            ),
        )
        job.next_run_at = job.compute_next_run(from_dt=now)
        job.save(update_fields=["next_run_at"])

    # executa os agendados
    for job in jobs_to_run:
        # evita concorrência
        if AutomationRun.objects.filter(job=job, status=AutomationRun.Status.RUNNING).exists():
            continue

        execute_job_async(
            job,
            triggered_by=None,
            triggered_mode=AutomationRun.TriggerMode.SCHEDULE,  # ✅ igual seu model
        )

        job.next_run_at = job.compute_next_run(from_dt=now)
        job.save(update_fields=["next_run_at"])


# ==========================
#  Pastas / venv
# ==========================

def get_job_folder(job: AutomationJob) -> Path:
    job_folder = AUTOMATION_ROOT / f"job_{job.id}"
    job_folder.mkdir(parents=True, exist_ok=True)

    readme = job_folder / "README.txt"
    if not readme.exists():
        readme.write_text(
            (
                "Pasta dedicada da automação.\n"
                "Coloque aqui:\n"
                "- requirements.txt (opcional)\n"
                "- script principal indicado em 'Arquivo principal (main)'\n"
                "- demais arquivos necessários.\n"
            ),
            encoding="utf-8",
        )

    return job_folder


def get_venv_python(job_folder: Path, buffer) -> str:
    """
    Garante que exista um .venv dentro da pasta do job e retorna o python do venv.
    """
    job_folder = Path(job_folder)
    venv_dir = job_folder / ".venv"

    if os.name == "nt":
        venv_python = venv_dir / "Scripts" / "python.exe"
    else:
        venv_python = venv_dir / "bin" / "python"

    if venv_python.exists():
        _log(buffer, f"[{timezone.now().isoformat()}] 📦 Ambiente virtual já existe: {venv_python}")
        return str(venv_python)

    base_python = sys.executable
    _log(buffer, f"[{timezone.now().isoformat()}] 📦 Criando ambiente virtual em: {venv_dir}")
    _log(buffer, f"[{timezone.now().isoformat()}] ▶️ Comando venv: {base_python} -m venv {venv_dir}")

    try:
        result = subprocess.run(
            [base_python, "-m", "venv", str(venv_dir)],
            capture_output=True,
            text=True,
            check=True,
        )
        if result.stdout:
            _log(buffer, result.stdout)
        if result.stderr:
            _log(buffer, result.stderr)
    except subprocess.CalledProcessError as e:
        _log(
            buffer,
            f"[{timezone.now().isoformat()}] ❌ Falha ao criar venv: {e}\n"
            f"STDOUT:\n{e.stdout}\n\nSTDERR:\n{e.stderr}",
        )
        raise

    return str(venv_python)


def install_requirements(job_folder: Path, venv_python, buffer) -> None:
    """
    Se existir requirements.txt dentro do job_folder, instala no venv do job.
    """
    job_folder = Path(job_folder)
    venv_python = Path(venv_python)
    requirements_file = job_folder / "requirements.txt"

    if not requirements_file.exists():
        _log(buffer, f"[{timezone.now().isoformat()}] ⚠️ Nenhum requirements.txt encontrado em: {requirements_file}")
        return

    # upgrade pip
    cmd1 = [str(venv_python), "-m", "pip", "install", "--upgrade", "pip"]
    _log(buffer, f"[{timezone.now().isoformat()}] ⚙️ Atualizando pip com: {' '.join(cmd1)}")
    r1 = subprocess.run(cmd1, cwd=job_folder, capture_output=True, text=True)
    if r1.stdout:
        _log(buffer, r1.stdout)
    if r1.stderr:
        _log(buffer, "----- STDERR (pip upgrade) -----\n" + r1.stderr)
    if r1.returncode != 0:
        raise RuntimeError(f"Falha ao atualizar pip (código {r1.returncode}).")

    # install requirements
    cmd2 = [str(venv_python), "-m", "pip", "install", "-r", str(requirements_file)]
    _log(buffer, f"[{timezone.now().isoformat()}] ⚙️ Instalando requirements com: {' '.join(cmd2)}")
    r2 = subprocess.run(cmd2, cwd=job_folder, capture_output=True, text=True)
    if r2.stdout:
        _log(buffer, r2.stdout)
    if r2.stderr:
        _log(buffer, "----- STDERR (pip install) -----\n" + r2.stderr)
    if r2.returncode != 0:
        raise RuntimeError(f"Falha ao instalar dependências (código {r2.returncode}).")

    # sanity check (opcional: você pode remover se quiser)
    cmd3 = [str(venv_python), "-c", "import selenium, pandas, openpyxl; print('deps_ok')"]
    r3 = subprocess.run(cmd3, cwd=job_folder, capture_output=True, text=True)
    if r3.stdout:
        _log(buffer, r3.stdout.strip())
    if r3.returncode != 0:
        _log(buffer, "----- STDERR (deps check) -----\n" + (r3.stderr or ""))
        raise RuntimeError("Dependências não importaram após instalar requirements (venv provavelmente corrompido).")


# ==========================
#  Execução da automação (pasta + venv)
# ==========================

def execute_external_folder_job(job: AutomationJob, run: AutomationRun, buffer) -> None:
    job_folder = get_job_folder(job)
    _log(buffer, f"[{timezone.now().isoformat()}] 📁 Pasta do job: {job_folder}")

    venv_python = get_venv_python(job_folder, buffer)
    install_requirements(job_folder, venv_python, buffer)

    main_script_name = job.external_main_script or "main.py"
    script_path = job_folder / main_script_name

    _log(buffer, f"[{timezone.now().isoformat()}] 📂 Diretório de trabalho: {job_folder}")
    _log(buffer, f"[{timezone.now().isoformat()}] ▶️ Comando: {venv_python} -u {script_path}")

    if not script_path.exists():
        raise FileNotFoundError(f"Script principal '{main_script_name}' não encontrado em {job_folder}")

    # -u = unbuffered (log aparece na hora)
    proc = subprocess.Popen(
        [str(venv_python), "-u", str(script_path)],
        cwd=str(job_folder),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    run.external_pid = proc.pid
    run.save(update_fields=["external_pid"])

    def _reader(pipe, label: str):
        try:
            for line in iter(pipe.readline, ""):
                _log(buffer, f"[{timezone.now().isoformat()}] {label}: {line.rstrip()}")
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    t_out = threading.Thread(target=_reader, args=(proc.stdout, "STDOUT"), daemon=True)
    t_err = threading.Thread(target=_reader, args=(proc.stderr, "STDERR"), daemon=True)
    t_out.start()
    t_err.start()

    returncode = proc.wait()
    t_out.join(timeout=2)
    t_err.join(timeout=2)

    _log(buffer, f"[{timezone.now().isoformat()}] 🏁 Script terminou com código de saída: {returncode}")

    if returncode != 0:
        raise RuntimeError(f"Script terminou com erro (código {returncode}). Verifique STDOUT/STDERR acima.")


# ==========================
#  Execução de Jobs
# ==========================

def execute_job(
    job: AutomationJob,
    triggered_by=None,
    triggered_mode: AutomationRun.TriggerMode | None = None,
) -> AutomationRun:

    if triggered_mode is None:
        triggered_mode = (
            AutomationRun.TriggerMode.MANUAL
            if triggered_by is not None
            else AutomationRun.TriggerMode.SCHEDULE
        )

    run = AutomationRun.objects.create(
        job=job,
        status=AutomationRun.Status.RUNNING,
        triggered_by=triggered_by,
        triggered_mode=triggered_mode,
        started_at=timezone.now(),
    )

    # evento de início (não derruba se falhar)
    try:
        if triggered_mode == AutomationRun.TriggerMode.MANUAL:
            log_automation_event(
                job,
                AutomationEvent.EventType.MANUAL_START,
                run=run,
                user=triggered_by,
                message="Execução manual iniciada.",
            )
        else:
            log_automation_event(
                job,
                AutomationEvent.EventType.SCHEDULE_TRIGGERED,
                run=run,
                user=triggered_by,
                message="Execução agendada iniciada pelo scheduler.",
            )
    except Exception:
        pass

    buffer = LiveRunLogger(run, flush_interval=1.0)
    buffer.write(
        f"[{timezone.now().isoformat()}] 🚀 Iniciando automação externa '{job.name}' (job_id={job.id}, run_id={run.id})\n"
    )
    buffer.flush()

    try:
        execute_external_folder_job(job, run, buffer)
        run.status = AutomationRun.Status.SUCCESS
        buffer.write(f"[{timezone.now().isoformat()}] ✅ Execução concluída com sucesso.\n")
    except Exception:
        run.status = AutomationRun.Status.FAILED
        buffer.write(f"[{timezone.now().isoformat()}] ❌ Erro inesperado na automação:\n")
        traceback.print_exc(file=buffer)

    # ✅ FINALIZA SEMPRE
    run.finished_at = timezone.now()
    buffer.flush()
    run.log = buffer.getvalue()
    run.save(update_fields=["status", "finished_at", "log"])
    return run


def execute_job_async(
    job: AutomationJob,
    *,
    triggered_by=None,
    triggered_mode: AutomationRun.TriggerMode | None = None,
) -> None:
    """Executa em thread para não travar request."""
    def _target():
        execute_job(job, triggered_by=triggered_by, triggered_mode=triggered_mode)

    threading.Thread(target=_target, daemon=True).start()


# ==========================
#  Helper: eventos
# ==========================

def log_automation_event(
    job: AutomationJob,
    event_type: str,
    *,
    run: AutomationRun | None = None,
    message: str = "",
    meta: dict | None = None,
    user=None,
):
    return AutomationEvent.objects.create(
        job=job,
        run=run,
        event_type=event_type,
        message=message or "",
        meta=meta or {},
        triggered_by=user,
    )
