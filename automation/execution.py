# automation/execution.py

"""
Camada de execução de automações.
"""

import os
import sys
import subprocess
from pathlib import Path
from importlib import import_module

from django.conf import settings
from django.utils import timezone

from .models import AutomationJob, AutomationRun


# -------------------------------------------------------------
# 1) Pasta de trabalho do job
# -------------------------------------------------------------
def get_job_workspace(job: AutomationJob) -> Path:
    base_dir = Path(settings.BASE_DIR)
    root = base_dir / "automation_jobs"

    if not job.pk:
        raise ValueError("O job precisa estar salvo (ter um ID) para ter uma pasta de workspace.")

    job_dir = root / f"job_{job.pk}"
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


# -------------------------------------------------------------
# 2) Helper de log centralizado para AutomationRun
# -------------------------------------------------------------
def make_run_logger(run: AutomationRun):
    def log(msg: str):
        # Garante que seja string
        msg_str = str(msg)
        
        # ISO simples só pra ficar padrinho
        ts = timezone.now().isoformat(timespec="seconds")
        # Verifica se a mensagem já tem quebra de linha no final para não duplicar
        line = f"[{ts}] {msg_str}"
        if not line.endswith('\n'):
            line += "\n"

        if not run.log:
            run.log = line
        else:
            run.log += line

        run.save(update_fields=["log"])
        print(line, end="") 

    return log


# -------------------------------------------------------------
# 3) Preparar venv para automação externa
# -------------------------------------------------------------
def prepare_venv_for_job(job: AutomationJob, log):
    job_dir = get_job_workspace(job)

    if not job.use_virtualenv:
        log("⚙️ job.use_virtualenv = False → usando Python do projeto.")
        return Path(sys.executable), job_dir

    venv_dir = job_dir / ".venv"

    if not venv_dir.exists():
        log(f"📦 Criando ambiente virtual em: {venv_dir}")
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            check=True,
        )
    else:
        log(f"📦 Ambiente virtual já existe: {venv_dir}")

    if os.name == "nt":
        venv_python = venv_dir / "Scripts" / "python.exe"
    else:
        venv_python = venv_dir / "bin" / "python"

    if not venv_python.exists():
        raise RuntimeError(f"Python do venv não encontrado em: {venv_python}")

    requirements_file = job_dir / (job.requirements_filename or "requirements.txt")
    if requirements_file.exists():
        log(f"📄 Encontrado requirements: {requirements_file}")

        cmd = [
            str(venv_python), "-m", "pip", "install", "--upgrade", "pip",
            "-r", str(requirements_file),
        ]
        log(f"⚙️ Instalando dependências...")

        # Aqui também usamos environment limpo se necessário, mas run simples resolve
        proc = subprocess.run(
            cmd,
            cwd=str(job_dir),
            text=True,
            capture_output=True,
        )

        if proc.stdout:
            log(proc.stdout)
        if proc.stderr:
            log(proc.stderr)

        if proc.returncode != 0:
            raise RuntimeError(f"Falha ao instalar requirements (código {proc.returncode})")
    else:
        log(f"⚠ Nenhum arquivo requirements encontrado.")

    return venv_python, job_dir


# -------------------------------------------------------------
# 4) Execução de job EXTERNO (CRÍTICO: ENV UNBUFFERED)
# -------------------------------------------------------------
def run_external_script(job: AutomationJob, run: AutomationRun):
    """
    Executa automação com STREAMING de logs via subprocess.Popen.
    """
    log = make_run_logger(run)

    log(f"🚀 Iniciando automação externa '{job.name}' (job_id={job.id}, run_id={run.id})")

    if not job.entrypoint:
        raise ValueError("Job sem entrypoint definido.")

    venv_python, job_dir = prepare_venv_for_job(job, log)

    script_path = job_dir / job.entrypoint
    if not script_path.exists():
        raise FileNotFoundError(f"Script '{job.entrypoint}' não encontrado.")

    # --- CORREÇÃO PRINCIPAL ---
    # Cria uma cópia das variáveis de ambiente e força o modo sem buffer
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    # O flag -u também ajuda, mantemos ele
    cmd = [str(venv_python), "-u", str(script_path)]
    
    log(f"📂 Workdir: {job_dir}")
    log(f"▶️ Cmd: {' '.join(cmd)}")
    log("----- INÍCIO DO STREAM DE LOGS -----\n")

    try:
        with subprocess.Popen(
            cmd,
            cwd=str(job_dir),
            env=env,                    # <--- Passamos o env modificado aqui
            stdout=subprocess.PIPE,     # Captura saída padrão
            stderr=subprocess.STDOUT,   # Redireciona erros (stderr) para o mesmo fluxo (stdout)
            text=True,                  # Texto (str)
            bufsize=1,                  # Buffer linha-a-linha
            encoding='utf-8',
            errors='replace'
        ) as proc:
            
            run.external_pid = proc.pid
            run.save(update_fields=["external_pid"])

            # Itera sobre cada linha assim que ela é emitida
            for line in proc.stdout:
                log(line) 
            
            return_code = proc.wait()

        log(f"\n🏁 Fim da execução. Código de saída: {return_code}")

        if return_code != 0:
            raise RuntimeError(f"Script terminou com erro (código {return_code}).")

    except Exception as e:
        raise e


# -------------------------------------------------------------
# 5) Execução de job INTERNO
# -------------------------------------------------------------
def run_internal_callable(job: AutomationJob, run: AutomationRun):
    log = make_run_logger(run)
    log(f"🚀 Iniciando automação interna '{job.name}' (job_id={job.id}, run_id={run.id})")

    module = import_module(job.module_path)
    func = getattr(module, job.callable_name, None)

    if func is None:
        raise AttributeError(
            f"Não foi possível encontrar '{job.callable_name}' em '{job.module_path}'."
        )

    func(run=run, log=log)


# -------------------------------------------------------------
# 6) Função central
# -------------------------------------------------------------
def execute_job(job: AutomationJob, run: AutomationRun):
    log = make_run_logger(run)

    if not run.started_at:
        run.started_at = timezone.now()
        run.status = "running"
        run.save(update_fields=["started_at", "status"])

    try:
        if job.job_type == AutomationJob.JOB_TYPE_EXTERNAL:
            run_external_script(job, run)
        else:
            run_internal_callable(job, run)

        run.status = "success"
        log("✅ Execução concluída com sucesso.")
    except Exception as exc:
        run.status = "failed"
        log(f"❌ Execução falhou: {exc}")
        raise
    finally:
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "finished_at"])