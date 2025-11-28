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


# ==========================
#  Caminhos básicos
# ==========================

# Raiz onde ficarão as pastas das automações
AUTOMATION_ROOT = Path(settings.BASE_DIR) / "automation_jobs"
AUTOMATION_ROOT.mkdir(parents=True, exist_ok=True)


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


def get_venv_python(job_folder: Path, buffer: io.StringIO) -> Path:
    """
    Garante que exista um .venv dentro da pasta da automação
    e devolve o caminho do python desse venv.
    """
    venv_dir = job_folder / ".venv"

    # Detecta se já existe
    if sys.platform.startswith("win"):
        python_path = venv_dir / "Scripts" / "python.exe"
    else:
        python_path = venv_dir / "bin" / "python"

    if python_path.exists():
        buffer.write(
            f"[{timezone.now().isoformat()}] 📦 Ambiente virtual já existe: {python_path.parent}\n"
        )
        return python_path

    # Criar venv
    buffer.write(
        f"[{timezone.now().isoformat()}] 📦 Criando ambiente virtual em: {venv_dir}\n"
    )
    venv_dir.mkdir(parents=True, exist_ok=True)

    # Usa o python do projeto para criar o venv
    cmd = [sys.executable, "-m", "venv", str(venv_dir)]
    buffer.write(
        f"[{timezone.now().isoformat()}] ▶️ Comando venv: {' '.join(cmd)}\n"
    )

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if proc.stdout:
        buffer.write(f"[{timezone.now().isoformat()}] venv STDOUT:\n{proc.stdout}\n")
    if proc.stderr:
        buffer.write(f"[{timezone.now().isoformat()}] venv STDERR:\n{proc.stderr}\n")

    if proc.returncode != 0:
        raise RuntimeError(
            f"Falha ao criar venv (código {proc.returncode}). Veja saída acima."
        )

    # Recalcula o caminho do python (por garantia)
    if sys.platform.startswith("win"):
        python_path = venv_dir / "Scripts" / "python.exe"
    else:
        python_path = venv_dir / "bin" / "python"

    if not python_path.exists():
        raise RuntimeError(f"Python do venv não encontrado em: {python_path}")

    return python_path


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

    # Execução do script
    proc = subprocess.run(
        [str(venv_python), str(script_path)],
        cwd=str(job_folder),
        capture_output=True,
        text=True,
    )

    # STDOUT / STDERR
    if proc.stdout:
        buffer.write(f"[{timezone.now().isoformat()}] ----- STDOUT -----\n")
        buffer.write(proc.stdout + "\n")
    if proc.stderr:
        buffer.write(f"[{timezone.now().isoformat()}] ----- STDERR -----\n")
        buffer.write(proc.stderr + "\n")

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
