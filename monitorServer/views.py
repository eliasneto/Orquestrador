# monitorServer/views.py
import os
import platform
import datetime as dt
import json   # 👈 novo
import psutil  # biblioteca de monitoramento do sistema

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST  # 👈 IMPORT IMPORTANTE

def get_top_processes(limit=10):
    """
    Retorna os 'limit' processos mais ofensores (ordenados por uso de CPU,
    e em seguida por uso de memória).
    """

    processes = []

    # process_iter é bem mais leve que rodar psutil.Process() em tudo manualmente
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info", "username"]):
        try:
            info = p.info
            mem_info = info.get("memory_info")
            mem_bytes = mem_info.rss if mem_info else 0

            processes.append({
                "pid": info.get("pid"),
                "name": info.get("name") or "(sem nome)",
                "cpu_percent": info.get("cpu_percent", 0.0),
                "memory_mb": round(mem_bytes / (1024 ** 2), 1),
                "username": info.get("username") or "",
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            # Processo sumiu ou não temos permissão -> ignora
            continue

    # Ordena: primeiro pela CPU, depois pela memória
    processes.sort(key=lambda p: (p["cpu_percent"], p["memory_mb"]), reverse=True)

    return processes[:limit]


def get_system_metrics():
    """
    Coleta as principais métricas do servidor onde o Django está rodando.

    Retorna um dicionário pronto para ser usado tanto na view HTML quanto na API.
    """

    # CPU (% de uso médio no momento)
    # interval=0.5 espera meio segundo para calcular a média
    cpu_percent = psutil.cpu_percent(interval=0.5)

    # Memória RAM
    vm = psutil.virtual_memory()
    mem_total_gb = vm.total / (1024 ** 3)
    mem_used_gb = vm.used / (1024 ** 3)
    mem_percent = vm.percent

    # Disco (por padrão, pega a unidade principal)
    if os.name == "nt":  # Windows
        disk_path = "C:\\"
    else:                # Linux / outros
        disk_path = "/"

    du = psutil.disk_usage(disk_path)
    disk_total_gb = du.total / (1024 ** 3)
    disk_used_gb = du.used / (1024 ** 3)
    disk_percent = du.percent

    # Número de processos
    process_count = len(psutil.pids())

    # Rede (contadores desde o boot)
    net_io = psutil.net_io_counters()
    bytes_sent_mb = net_io.bytes_sent / (1024 ** 2)
    bytes_recv_mb = net_io.bytes_recv / (1024 ** 2)

    # Uptime (tempo desde o último boot)
    boot_ts = psutil.boot_time()
    boot_dt = dt.datetime.fromtimestamp(boot_ts)
    now = dt.datetime.now()
    uptime = now - boot_dt  # timedelta

    # Formata uptime em algo legível (dias, horas, minutos)
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    uptime_str = f"{days}d {hours}h {minutes}min"

    # Último boot = "quando o servidor subiu"
    last_boot_str = boot_dt.strftime("%d/%m/%Y %H:%M:%S")

    # Obs.: "último desligamento" exato é mais complexo (depende de logs do SO).
    # Para a maioria dos casos, o mais útil é "último boot", que é o que temos aqui.

    # Informações básicas do sistema operacional
    sys_info = {
        "system": platform.system(),
        "node": platform.node(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
    }

    return {
        "cpu": {
            "percent": round(cpu_percent, 1),
        },
        "memory": {
            "total_gb": round(mem_total_gb, 2),
            "used_gb": round(mem_used_gb, 2),
            "percent": round(mem_percent, 1),
        },
        "disk": {
            "mount": disk_path,
            "total_gb": round(disk_total_gb, 2),
            "used_gb": round(disk_used_gb, 2),
            "percent": round(disk_percent, 1),
        },
        "processes": {
            "count": process_count,
        },
        "network": {
            # valores acumulados desde o boot
            "bytes_sent_mb": round(bytes_sent_mb, 2),
            "bytes_recv_mb": round(bytes_recv_mb, 2),
        },
        "uptime": {
            "human": uptime_str,
            "boot_time": last_boot_str,
        },
        "system": sys_info,
        "collected_at": now.strftime("%d/%m/%Y %H:%M:%S"),

        "top_processes": get_top_processes(10),
    }


class SystemHealthView(LoginRequiredMixin, TemplateView):
    """
    Página HTML que mostra a saúde do servidor em cards.
    Apenas usuários logados podem ver.
    """
    template_name = "monitor/system_health.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["metrics"] = get_system_metrics()
        return ctx


@login_required
def system_health_api(request):
    """
    Endpoint JSON para retornar as métricas.

    Pode ser usado pelo frontend (AJAX) ou por outros sistemas.
    """
    metrics = get_system_metrics()
    return JsonResponse(metrics)


@require_POST
@login_required
def kill_process_api(request):
    """
    Encerra um processo pelo PID.

    - Apenas usuários staff podem usar.
    - Usa psutil para fazer terminate() e, se precisar, kill().

    Corpo JSON esperado: {"pid": 1234}
    """

    if not request.user.is_staff:
        return JsonResponse({"error": "Permissão negada (apenas staff)."}, status=403)

    try:
        data = json.loads(request.body.decode("utf-8"))
        pid = int(data.get("pid"))

        if pid <= 0:
            return JsonResponse({"error": "PID inválido."}, status=400)

        proc = psutil.Process(pid)
        proc.terminate()  # tenta encerrar “educadamente”
        try:
            proc.wait(timeout=3)
        except psutil.TimeoutExpired:
            proc.kill()   # se não morrer, mata na força

        return JsonResponse({"status": "ok", "pid": pid})
    except psutil.NoSuchProcess:
        return JsonResponse({"error": "Processo não existe mais."}, status=404)
    except psutil.AccessDenied:
        return JsonResponse({"error": "Acesso negado para esse processo."}, status=403)
    except Exception as e:
        return JsonResponse({"error": f"Erro inesperado: {e}"}, status=500)

