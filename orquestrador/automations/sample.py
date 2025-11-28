# orquestrador/automations/sample.py
"""
Script de automação de exemplo.

Use para testar o módulo de automação antes de plugar seus robôs reais.
"""

import time
from datetime import datetime


def run():
    """
    Função de entrada da automação.

    Importante: o módulo de automação espera que esta função exista
    e seja chamável.
    """
    print(f"[{datetime.now()}] Iniciando automação de teste...")
    time.sleep(2)
    print(f"[{datetime.now()}] Processando alguma coisa fictícia...")
    time.sleep(2)
    print(f"[{datetime.now()}] Automação de teste finalizada.")
