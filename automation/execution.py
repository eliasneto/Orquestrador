# automation/execution.py

"""
Camada de execução de automações.

Responsável por:
- Descobrir a pasta de trabalho de cada AutomationJob;
- Criar ambiente virtual (venv) por automação externa;
- Instalar requirements.txt dentro desse venv;
- Executar o script principal da automação externa via subprocess;
- Executar jobs internos (module_path + callable_name);
- Gravar logs e status na AutomationRun.

Tudo bem comentado para futuras manutenções.
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
    """
    Retorna o caminho da pasta onde ficam os arquivos dessa automação.

    Padrão:
        <BASE_DIR>/automation_jobs/job_<id>/

    Exemplo:
        C:\...\Orquestrador\automation_jobs\job_5\
        /app/automation_jobs/job_5/
    """
    base_dir = Path(settings.BASE_DIR)
    root = base_dir / "automation_jobs"

    if not job.pk:
        # job precisa ter sido salvo pra ter ID
        raise ValueError("O job precisa estar salvo (ter um ID) para ter uma pasta de workspace.")

    job_dir = root / f"job_{job.pk}"
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


# -------------------------------------------------------------
# 2) Helper de log centralizado para AutomationRun
# -------------------------------------------------------------
def make_run_logger(run: AutomationRun):
    """
    Cria uma função log(msg: str) que:

    - Prepara a linha com timestamp;
    - Concatena no campo 'log' da AutomationRun;
    - Dá um save(update_fields=["log"]) pra ficar leve;
    - Imprime no stdout (bom pra ver pelo docker logs).
    """

    def log(msg: str):
        # ISO simples só pra ficar padrinho
        ts = timezone.now().isoformat(timespec="seconds")
        line = f"[{ts}] {msg}\n"

        if not run.log:
            run.log = line
        else:
            run.log += line

        run.save(update_fields=["log"])
        print(line, end="")  # aparece no log do servidor / container

    return log


# -------------------------------------------------------------
# 3) Preparar venv para automação externa
# -------------------------------------------------------------
def prepare_venv_for_job(job: AutomationJob, log):
    """
    Garante que o ambiente virtual (.venv) da automação exista e,
    se existir um requirements.txt, instala as dependências.

    Retorna:
        (venv_python: Path, job_dir: Path)

    - Se job.use_virtualenv = False -> usa o Python do projeto (sys.executable)
      e apenas devolve a pasta do job.
    """
    job_dir = get_job_workspace(job)

    if not job.use_virtualenv:
        log("⚙️ job.use_virtualenv = False → usando Python do projeto (sem venv dedicado).")
        return Path(sys.executable), job_dir

    # Caminho do venv: <job_dir>/.venv
    venv_dir = job_dir / ".venv"

    # 1) Cria o venv se ainda não existir
    if not venv_dir.exists():
        log(f"📦 Criando ambiente virtual em: {venv_dir}")
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            check=True,
        )
    else:
        log(f"📦 Ambiente virtual já existe: {venv_dir}")

    # 2) Descobre o executável do Python dentro do venv (Windows x Linux)
    if os.name == "nt":
        venv_python = venv_dir / "Scripts" / "python.exe"
    else:
        venv_python = venv_dir / "bin" / "python"

    if not venv_python.exists():
        raise RuntimeError(f"Python do venv não encontrado em: {venv_python}")

    # 3) Instala requirements, se existir
    requirements_file = job_dir / (job.requirements_filename or "requirements.txt")
    if requirements_file.exists():
        log(f"📄 Encontrado requirements: {requirements_file}")

        cmd = [
            str(venv_python),
            "-m", "pip",
            "install",
            "--upgrade",
            "pip",
            "-r",
            str(requirements_file),
        ]
        log(f"⚙️ Instalando dependências com: {' '.join(cmd)}")

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
        log(
            f"⚠ Nenhum arquivo de requirements encontrado em: {requirements_file}. "
            "Seguindo sem instalar dependências extras."
        )

    return venv_python, job_dir


# -------------------------------------------------------------
# 4) Execução de job EXTERNO (pasta + venv + script principal)
# -------------------------------------------------------------
def run_external_script(job: AutomationJob, run: AutomationRun):
    """
    Executa uma automação do tipo 'external_script':

    - Descobre/Cria pasta do job;
    - Prepara venv se configurado;
    - Roda o script de entrada (entrypoint) via subprocess;
    - Joga stdout/stderr no log da AutomationRun;
    - Lança erro se o código de saída for != 0.
    """
    log = make_run_logger(run)

    log(f"🚀 Iniciando automação externa '{job.name}' (job_id={job.id}, run_id={run.id})")

    if not job.entrypoint:
        raise ValueError(
            "Para jobs do tipo 'Script externo' é obrigatório informar o campo 'entrypoint' "
            "(nome do arquivo principal, ex: main.py)."
        )

    # Prepara venv (ou usa Python do projeto)
    venv_python, job_dir = prepare_venv_for_job(job, log)

    script_path = job_dir / job.entrypoint
    if not script_path.exists():
        raise FileNotFoundError(
            f"Arquivo de entrada '{job.entrypoint}' não encontrado em: {job_dir}"
        )

    cmd = [str(venv_python), str(script_path)]
    log(f"📂 Diretório de trabalho: {job_dir}")
    log(f"▶️ Comando: {' '.join(cmd)}")

    proc = subprocess.run(
        cmd,
        cwd=str(job_dir),
        text=True,
        capture_output=True,
    )

    if proc.stdout:
        log("----- STDOUT -----")
        log(proc.stdout)
    if proc.stderr:
        log("----- STDERR -----")
        log(proc.stderr)

    log(f"🏁 Script terminou com código de saída: {proc.returncode}")

    if proc.returncode != 0:
        raise RuntimeError(f"Script externo terminou com erro (código {proc.returncode}).")


# -------------------------------------------------------------
# 5) Execução de job INTERNO (module_path + callable_name)
# -------------------------------------------------------------
def run_internal_callable(job: AutomationJob, run: AutomationRun):
    """
    Mantém compatibilidade com o modelo anterior:

    - Importa o módulo (job.module_path);
    - Pega a função (job.callable_name);
    - Chama a função.

    Aqui eu assumo que sua função de automação interna aceita
    parâmetros (run, log). Se for diferente, você pode adaptar.
    """
    log = make_run_logger(run)
    log(f"🚀 Iniciando automação interna '{job.name}' (job_id={job.id}, run_id={run.id})")

    module = import_module(job.module_path)
    func = getattr(module, job.callable_name, None)

    if func is None:
        raise AttributeError(
            f"Não foi possível encontrar '{job.callable_name}' em '{job.module_path}'."
        )

    # Chamada "padrão" sugerida: sua função recebe run e log
    func(run=run, log=log)


# -------------------------------------------------------------
# 6) Função central de execução (decide interna x externa)
# -------------------------------------------------------------
def execute_job(job: AutomationJob, run: AutomationRun):
    """
    Função central de execução.

    - Marca run como 'running';
    - Decide se job é INTERNAL ou EXTERNAL;
    - Chama o executor correto;
    - Atualiza status para success/failed e finished_at;
    - Deixa a exceção “subir” para o chamador se der erro (mas com log gravado).
    """
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
        # Aqui você pode querer logar traceback também, se achar necessário
        raise
    finally:
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "finished_at"])
