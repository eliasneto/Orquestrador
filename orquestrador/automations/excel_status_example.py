from pathlib import Path
from datetime import datetime

import pandas as pd
from django.conf import settings


def run():
    """
    Automação de exemplo que:
    - Garante a existência de um arquivo Excel base
      em automation_data/excel_example/clientes_pendentes.xlsx
    - Lê o arquivo
    - Marca todos os registros como 'processado' na coluna 'status'
    - Salva um novo Excel de saída com timestamp no nome

    Toda saída é feita com print(), que o Orquestrador captura.
    """

    print("🚀 Iniciando automação: Atualizar status Excel")
    print("==============================================")

    # 1) BASE_DIR do projeto (onde está o manage.py)
    base_dir = Path(settings.BASE_DIR)

    # 2) Pasta onde ficam os dados desta automação
    data_dir = base_dir / "automation_data" / "excel_example"
    data_dir.mkdir(parents=True, exist_ok=True)

    # 3) Arquivo de entrada (base) e arquivo de saída
    input_file = data_dir / "clientes_pendentes.xlsx"
    output_file = data_dir / f"clientes_pendentes_atualizado_{datetime.now():%Y%m%d_%H%M%S}.xlsx"

    print(f"📁 Pasta de dados: {data_dir}")
    print(f"📄 Arquivo de entrada esperado: {input_file}")
    print("")

    # 4) Se o arquivo base ainda não existir, cria um Excel de exemplo
    if not input_file.exists():
        print("⚠ Arquivo de entrada NÃO encontrado.")
        print("   Vou criar um arquivo de exemplo automaticamente...")

        df_exemplo = pd.DataFrame(
            [
                {"id": 1, "nome": "João da Silva", "status": ""},
                {"id": 2, "nome": "Maria Oliveira", "status": ""},
                {"id": 3, "nome": "Cliente OK", "status": "ok"},
            ]
        )

        # Cria um Excel .xlsx válido usando openpyxl
        df_exemplo.to_excel(input_file, index=False, engine="openpyxl")

        print(f"✅ Arquivo de exemplo criado em: {input_file}")
        print("   Estrutura das colunas:", list(df_exemplo.columns))
        print("")

    try:
        # 5) Ler Excel (que agora com certeza existe e é .xlsx válido)
        print("📥 Lendo arquivo de entrada...")
        df = pd.read_excel(input_file, engine="openpyxl")
        print("✅ Arquivo carregado com sucesso!")
        print(f"   Linhas: {len(df)}")
        print(f"   Colunas: {list(df.columns)}")
        print("")

        # 6) Garante a coluna 'status'
        if "status" not in df.columns:
            print("🛈 Coluna 'status' não encontrada. Criando coluna nova...")
            df["status"] = ""

        # 7) Atualiza coluna 'status'
        print("✍️ Atualizando coluna 'status' para 'processado'...")
        df["status"] = "processado"

        # 8) Salvar Excel de saída
        print("")
        print(f"💾 Salvando arquivo atualizado em:\n   {output_file}")
        df.to_excel(output_file, index=False, engine="openpyxl")
        print("✅ Arquivo salvo com sucesso!")
        print("")
        print("🎉 Automação concluída com sucesso.")

    except Exception as e:
        # Se der erro, mostra tudo no log
        print("❌ Erro inesperado na automação:")
        print(f"   Tipo: {type(e).__name__}")
        print(f"   Detalhes: {e}")
        # Relevanta para o Orquestrador marcar como FALHA
        raise
