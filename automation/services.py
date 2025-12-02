# automation/services.py
"""
Serviços de execução de automações.

Versão simplificada: **somente modelo pasta + venv**.

Fluxo:
- Cada AutomationJob tem uma pasta dedicada: BASE/automation_jobs/job_<id>/
- Dentro dessa pasta o usuário pode colocar:
    - requirements.txt  (opcional)
    - main.py           (ou outro nome definido em external_main_script)
    - quaisquer outros arquivos necessários

Quando uma automação é executada:
1) Garante que a pasta do job existe.
2) Garante que exista um .venv dentro da pasta (cria se não existir).
3) Se existir requirements.txt, instala/atualiza as libs nesse venv.
4) Executa o script principal usando o python do venv.
5) Salva STDOUT/STDERR no campo log de AutomationRun.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import threading
import traceback
from pathlib import Path
from typing import Optional
from django.conf import settings
from django.utils import timezone
from .models import AutomationJob, AutomationRun
#from .runner import disparar_job_externo  # sua função que dispara a automação

# ==========================
#  Caminhos básicos
# ==========================

# Raiz onde ficarão as pastas das automações
AUTOMATION_ROOT = Path(settings.BASE_DIR) / "automation_jobs"
AUTOMATION_ROOT.mkdir(parents=True, exist_ok=True)

# automation/services.py

def run_pending_jobs():
    """
    Dispara automaticamente os jobs agendados cujo next_run_at já passou.
    Deve ser chamada periodicamente (ex.: a cada 1 minuto).
    """
    now = timezone.now()

    # Busca jobs ativos que têm próxima execução definida e já vencida
    jobs = (
        AutomationJob.objects.filter(is_active=True)
        .exclude(next_run_at__isnull=True)
        .filter(next_run_at__lte=now)
    )

    for job in jobs:
        # Evita concorrência: se já tem uma execução rodando, pula esse job
        if AutomationRun.objects.filter(
            job=job,
            status=AutomationRun.Status.RUNNING,
        ).exists():
            continue

        # Dispara a execução em modo "agendado"
        execute_job_async(
            job,
            triggered_by=None,
            triggered_mode=AutomationRun.TriggerMode.SCHEDULE,
        )

        # Calcula e salva a próxima execução
        job.next_run_at = job.compute_next_run(from_dt=now)
        job.save(update_fields=["next_run_at"])


def get_job_folder(job: AutomationJob) -> Path:
    """
    Retorna a pasta da automação:
        <BASE_DIR>/automation_jobs/job_<id>/
    Cria se não existir.
    """
    job_folder = AUTOMATION_ROOT / f"job_{job.id}"
    job_folder.mkdir(parents=True, exist_ok=True)

    # Criar um README simples na primeira vez
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

def _log(buffer, msg: str):
    """
    Escreve no buffer de log tanto se for StringIO quanto se for lista.
    """
    line = msg + "\n"
    if hasattr(buffer, "write"):
        buffer.write(line)      # StringIO, arquivo etc.
    elif hasattr(buffer, "append"):
        buffer.append(line)     # lista de strings
    # se não for nenhum dos dois, ignora silenciosamente


def get_venv_python(job_folder: Path, buffer) -> str:
    """
    Garante que exista um .venv dentro da pasta do job e
    retorna o caminho para o executável python desse venv.
    """

    job_folder = Path(job_folder)
    venv_dir = job_folder / ".venv"

    # Caminho do python *dentro* do venv
    if os.name == "nt":
        venv_python = venv_dir / "Scripts" / "python.exe"
    else:
        venv_python = venv_dir / "bin" / "python"

    # Se o venv já existir, só registra no log e retorna
    if venv_python.exists():
        _log(
            buffer,
            f"[{timezone.now().isoformat()}] 📦 Ambiente virtual já existe: {venv_python}",
        )
        return str(venv_python)

    # Senão, cria o venv usando o python atual do Django (sys.executable)
    base_python = sys.executable
    _log(
        buffer,
        f"[{timezone.now().isoformat()}] 📦 Criando ambiente virtual em: {venv_dir}",
    )
    _log(
        buffer,
        f"[{timezone.now().isoformat()}] ▶️ Comando venv: {base_python} -m venv {venv_dir}",
    )

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
        # Repassa o erro pra quem chamou tratar
        raise

    return str(venv_python)


def install_requirements(job_folder: Path, venv_python: Path, buffer: io.StringIO) -> None:
    """
    Se existir requirements.txt na pasta da automação, instala/atualiza
    as dependências dentro do venv.
    """
    req_file = job_folder / "requirements.txt"
    if not req_file.exists():
        buffer.write(
            f"[{timezone.now().isoformat()}] 📄 Nenhum requirements.txt encontrado, pulando instalação.\n"
        )
        return

    buffer.write(
        f"[{timezone.now().isoformat()}] 📄 Encontrado requirements: {req_file}\n"
    )

    # Comando simples: atualizar pip + instalar deps
    cmd = [
        str(venv_python),
        "-m",
        "pip",
        "install",
        "--upgrade",
        "pip",
        "-r",
        str(req_file),
    ]
    buffer.write(
        f"[{timezone.now().isoformat()}] ⚙️ Instalando dependências com: {' '.join(cmd)}\n"
    )

    proc = subprocess.run(
        cmd,
        cwd=str(job_folder),
        capture_output=True,
        text=True,
    )

    if proc.stdout:
        buffer.write(f"[{timezone.now().isoformat()}] {proc.stdout}\n")
    if proc.stderr:
        buffer.write(f"[{timezone.now().isoformat()}] {proc.stderr}\n")

    if proc.returncode != 0:
        raise RuntimeError(
            f"Falha ao instalar dependências (código {proc.returncode})."
        )


def execute_external_folder_job(
    job: AutomationJob,
    run: AutomationRun,
    buffer: io.StringIO,
) -> None:
    """
    Executa o script principal da pasta da automação, usando o venv dedicado.

    - Garante pasta do job
    - Garante venv
    - Instala requirements (se houver)
    - Executa <venv_python> <script>
    """
    job_folder = get_job_folder(job)

    # 1) Venv
    buffer.write(
        f"[{timezone.now().isoformat()}] 📁 Pasta do job: {job_folder}\n"
    )

    venv_python = get_venv_python(job_folder, buffer)

    # 2) Instalar requirements, se existir
    install_requirements(job_folder, venv_python, buffer)

    # 3) Script principal
    main_script_name = job.external_main_script or "main.py"
    script_path = job_folder / main_script_name

    buffer.write(
        f"[{timezone.now().isoformat()}] 📂 Diretório de trabalho: {job_folder}\n"
    )
    buffer.write(
        f"[{timezone.now().isoformat()}] ▶️ Comando: {venv_python} {script_path}\n"
    )

    if not script_path.exists():
        raise FileNotFoundError(
            f"Script principal '{main_script_name}' não encontrado em {job_folder}"
        )

    # ==========================
    # Execução do script (Popen para permitir cancelamento)
    # ==========================
    proc = subprocess.Popen(
        [str(venv_python), str(script_path)],
        cwd=str(job_folder),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # 👇 Salva o PID no registro da execução
    run.external_pid = proc.pid
    run.save(update_fields=["external_pid"])

    # Espera terminar e captura STDOUT/STDERR
    stdout, stderr = proc.communicate()

    if stdout:
        buffer.write(f"[{timezone.now().isoformat()}] ----- STDOUT -----\n")
        buffer.write(stdout + "\n")
    if stderr:
        buffer.write(f"[{timezone.now().isoformat()}] ----- STDERR -----\n")
        buffer.write(stderr + "\n")

    buffer.write(
        f"[{timezone.now().isoformat()}] 🏁 Script terminou com código de saída: {proc.returncode}\n"
    )

    if proc.returncode != 0:
        raise RuntimeError(
            f"Script terminou com erro (código {proc.returncode}). Verifique STDOUT/STDERR acima."
        )


# ==========================
#  Execução de Jobs
# ==========================


# ==========================
#  Execução de Jobs
# ==========================


def execute_job(
    job: AutomationJob,
    triggered_by=None,
    triggered_mode: AutomationRun.TriggerMode | None = None,
) -> AutomationRun:
    """
    Executa UMA automação (modelo pasta + venv) de forma síncrona.

    - Cria AutomationRun
    - Executa a automação
    - Atualiza status, horários e log

    Regras para `triggered_mode`:
    - Se não informado e houver `triggered_by`  → MANUAL
    - Se não informado e não houver usuário    → SCHEDULED (agendado/sistema)
    """

    # Decide o modo padrão se não foi passado
    if triggered_mode is None:
        if triggered_by is not None:
            triggered_mode = AutomationRun.TriggerMode.MANUAL
        else:
            triggered_mode = AutomationRun.TriggerMode.SCHEDULED

    # Cria o registro de execução
    run = AutomationRun.objects.create(
        job=job,
        status=AutomationRun.Status.RUNNING,
        triggered_by=triggered_by,
        triggered_mode=triggered_mode,
        started_at=timezone.now(),  # evita NOT NULL
    )

    buffer = io.StringIO()
    ts = timezone.now().isoformat()
    buffer.write(
        f"[{ts}] 🚀 Iniciando automação externa '{job.name}' (job_id={job.id}, run_id={run.id})\n"
    )

    try:
        # 🔧 aqui é o ponto em que de fato invocamos a pasta + venv
        execute_external_folder_job(job, run, buffer)
        run.status = AutomationRun.Status.SUCCESS
        buffer.write(
            f"[{timezone.now().isoformat()}] ✅ Execução concluída com sucesso.\n"
        )
    except Exception:
        run.status = AutomationRun.Status.FAILED
        buffer.write(
            f"[{timezone.now().isoformat()}] ❌ Erro inesperado na automação:\n"
        )
        traceback.print_exc(file=buffer)

    run.finished_at = timezone.now()
    # agrega log ao campo log
    run.log = (run.log or "") + "\n" + buffer.getvalue()
    run.save(update_fields=["status", "finished_at", "log"])
    return run


def execute_job_async(
    job: AutomationJob,
    *,
    triggered_by=None,
    triggered_mode: AutomationRun.TriggerMode | None = None,
) -> None:
    """
    Dispara a execução em segundo plano (thread), para não travar o request.

    Se `triggered_mode` vier como None, o `execute_job` vai aplicar
    a mesma regra de MANUAL/SCHEDULED automaticamente.
    """

    def _target():
        execute_job(
            job,
            triggered_by=triggered_by,
            triggered_mode=triggered_mode,
        )

    t = threading.Thread(target=_target, daemon=True)
    t.start()
