from pathlib import Path
from datetime import datetime
import requests  # só pra garantir que o requirements foi instalado

BASE_DIR = Path(__file__).resolve().parent

print("=== Script externo executado com sucesso! ===")
print("Pasta de trabalho:", BASE_DIR)
print("Versão do requests:", requests.__version__)

log_file = BASE_DIR / "external_log.txt"

with log_file.open("a", encoding="utf-8") as f:
    f.write(
        f"[{datetime.now().isoformat(sep=' ', timespec='seconds')}] "
        f"Execução OK. Versão requests: {requests.__version__}\n"
    )

print("Log gravado em:", log_file)
