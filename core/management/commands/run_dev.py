# core/management/commands/run_dev.py

from django.core.management.commands.runserver import Command as RunserverCommand


class Command(RunserverCommand):
    help = "Runserver com banner customizado do Orquestrador"

    def inner_run(self, *args, **options):
        from django.conf import settings

        # 1) Descobrir host/porta que o runserver está usando
        addrport = options.get("addrport") or ""
        if addrport:
            if ":" in addrport:
                host, port = addrport.split(":", 1)
            else:
                host, port = "127.0.0.1", addrport
        else:
            host, port = self.default_addr, self.default_port

        # 👇 Aqui decidimos o que MOSTRAR no banner
        display_host = host
        if host == "0.0.0.0":
            # para o usuário clicar, é melhor localhost
            display_host = "localhost"

        base_url = f"http://{display_host}:{port}/"

        dashboard_url = base_url          # home
        automations_url = f"{base_url}automation/"
        server_health_url = f"{base_url}monitor/server-health/"

        # 3) Banner customizado
        self.stdout.write("")
        self.stdout.write(self.style.WARNING("══════════════════════════════════════════"))
        self.stdout.write(self.style.SUCCESS("   🧠 ORQUESTRADOR – Speed Tecnologia"))
        self.stdout.write(self.style.WARNING("══════════════════════════════════════════"))
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO(f"   🌐 Dashboard:       {dashboard_url}"))
        self.stdout.write(self.style.HTTP_INFO(f"   🤖 Automações:      {automations_url}"))
        self.stdout.write(self.style.HTTP_INFO(f"   🖥️ Saúde Servidor:  {server_health_url}"))
        self.stdout.write("")
        self.stdout.write(self.style.NOTICE(
            "   Pressione CTRL+C para parar o servidor."
        ))
        self.stdout.write("")

        # 4) Chama o comportamento normal do runserver
        return super().inner_run(*args, **options)
