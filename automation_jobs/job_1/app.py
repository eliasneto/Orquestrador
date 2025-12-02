from selene import browser, be, by, have
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver import ActionChains
import time
from selenium.webdriver.common.keys import Keys
import os
import shutil
import sys  # 👈 IMPORTANTE para conseguir encerrar o script
from datetime import datetime
from dados_planilha import carregar_dados
import pandas as pd
from selene.core.exceptions import TimeoutException

# === NOVO: flag para controlar se vai rodar com ou sem janela ===
MODO_HEADLESS = False  # True = sem janela (headless) | False = com janela


# ============================
# Carrega os dados da planilha Excel
# ============================
CAMINHO_PLANILHA = r"entrada\entrada.xlsx"
dados = carregar_dados(CAMINHO_PLANILHA)

print(f"📘 {len(dados)} registro(s) carregado(s) da planilha: {CAMINHO_PLANILHA}")

# Pasta de saída para o CSV de resultado
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PASTA_SAIDA = os.path.join(BASE_DIR, "saida")
os.makedirs(PASTA_SAIDA, exist_ok=True)

# Lista onde vamos acumular o status de cada registro
RESULTADOS = []


# 🔴 Se não tiver nenhum registro, para tudo aqui
if not dados:
    print("⚠️ Nenhum registro encontrado na planilha.")
    print("   ➤ Verifique se a planilha tem pelo menos uma linha preenchida (aba correta, sem filtros).")
    sys.exit(1)

# Se chegou até aqui, tem pelo menos 1 linha
registro = dados[0]  # usa a primeira linha (pode ser feito loop depois)
print("📘 Dados carregados da primeira linha:", registro)

# --- setup ---
options = Options()
if MODO_HEADLESS:
    options.add_argument('--headless=new')      # roda o Chrome sem abrir janela
    options.add_argument('--window-size=1280,800')  # garante um tamanho fixo de viewport
else:
    options.add_experimental_option('detach', True)  # mantém a janela aberta após o script

browser.config.driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options
)

browser.config.timeout = 10
browser.config.window_width = 1280
browser.config.window_height = 800

# === ALTERADO: em headless não faz sentido segurar o browser aberto ===
browser.config.hold_browser_open = not MODO_HEADLESS


# --- login ---
browser.open('https://app.blueez.com.br/')
print("URL -> https://app.blueez.com.br/")
time.sleep(3)
browser.element('[name="j_username"]').should(be.visible).type('elias.neto@speedcsc.com.br').press_tab()
print("Usuario -> Usuario digitado")
time.sleep(3)
browser.element('[name="j_password"]').type('Gustavo@1025').press_enter()
print("Senha -> Senha digitada")
time.sleep(3)

# Espera o menu lateral
browser.element('#sidebarMenu, nav#sidebarMenu, .wrapperSidebarMenu').should(be.visible)
print("Menu aberto")
time.sleep(3)

# ======= FUNÇÕES AUXILIARES DE DATA / COMPETÊNCIA =======

def formatar_data(valor):
    # Se vier como Timestamp/datetime, formata só a data
    if isinstance(valor, (pd.Timestamp, datetime)):
        return valor.strftime('%d/%m/%Y')
    return str(valor)

def preencher_campo(seletor, valor):
    valor_str = formatar_data(valor)
    campo = browser.element(seletor).should(be.present)
    browser.driver.execute_script("""
        const campo = arguments[0];
        campo.value = arguments[1];
        campo.dispatchEvent(new Event('change', { bubbles: true }));
    """, campo(), valor_str)
    print(f"Campo {seletor} preenchido com: {valor_str}")
    time.sleep(1)

def formatar_competencia(valor):
    # Se vier como Timestamp/datetime, pega só mês/ano
    if isinstance(valor, (pd.Timestamp, datetime)):
        return valor.strftime('%m/%Y')

    s = str(valor).strip()
    if not s:
        return ""

    # Se já vier algo tipo "11/2025" ou "8/2025"
    partes = s.split('/')
    if len(partes) == 2 and len(partes[1]) == 4:
        mes, ano = partes
        try:
            mes_int = int(mes)
            if 1 <= mes_int <= 12:
                return f"{mes_int:02d}/{ano}"
        except ValueError:
            pass

    # Se vier como data completa, tenta converter
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime('%m/%Y')
        except ValueError:
            pass

    # Se nada der certo, devolve como está (pra não quebrar)
    return s

def preencher_competencia(seletor, valor):
    valor_str = formatar_competencia(valor)
    campo = browser.element(seletor).should(be.present)
    browser.driver.execute_script("""
        const campo = arguments[0];
        campo.value = arguments[1];
        campo.dispatchEvent(new Event('change', { bubbles: true }));
    """, campo(), valor_str)
    print(f"Campo {seletor} (competência) preenchido com: {valor_str}")
    time.sleep(1)

# ============================
# NOVO: loop sobre TODOS os registros da planilha
# ============================
total_registros = len(dados)

for indice_registro, registro in enumerate(dados, start=1):
    # copia os dados originais pra registrar no CSV
    resultado = dict(registro)
    resultado["registro"] = indice_registro  # número da linha que foi processada

    try:
        print(f"\n================= Iniciando registro {indice_registro}/{total_registros} =================")
        print("📘 Registro atual:", registro)

        # ========= MENU MEDIÇÃO (mais robusto) =========
        print("CHECKPOINT 1 - Acessando submenu Medição")

        dropdown_medicao = browser.element(
            'a.dropdownSidebar-toggle[aria-controls="pageSubmenu30"]'
        ).should(be.present)

        # Só clica para abrir se ainda não estiver visível
        if not browser.element('#pageSubmenu30').matching(be.visible):
            dropdown_medicao.should(be.clickable).click()

        browser.element('#pageSubmenu30').should(be.visible)

        medicao = browser.element(
            by.xpath('//*[@id="pageSubmenu30"]//span[normalize-space()="Medição"]')
        )
        medicao.should(be.clickable).click()
        print("Sub-Menu: Medição de Contratos")
        time.sleep(3)

        # Entra no iframe principal
        print("CHECKPOINT 2 - Antes de entrar no iframe")
        browser.element('iframe#iframeContent').should(be.present)
        browser.driver.switch_to.frame(browser.element('iframe#iframeContent')())
        print("Tela de fluxo: Medição de Contratos (dentro do iframe)")
        time.sleep(3)

        # Novo
        browser.element('#new_flow').should(be.clickable).click()
        browser.element('.modal.fade.show').should(be.visible)
        print("Criar nova solicitação de medição")
        time.sleep(3)

        # ============================
        # Empresa
        # ============================
        print("CHECKPOINT 3 - Empresa")
        
        lupa_empresa = browser.element('button[data-target="#modal_zoom_empresa_medicao_1"]').should(be.present)
        browser.driver.execute_script("arguments[0].scrollIntoView(true);", lupa_empresa())
        browser.driver.execute_script("arguments[0].click();", lupa_empresa())
        time.sleep(2)
        browser.element('#modal_zoom_empresa_medicao_1').should(be.visible)
        campo_busca = browser.element('#modal_zoom_empresa_medicao_1 input.form-control[placeholder="Procurar"]')
        campo_busca.should(be.visible).type(registro['empresa']).press_enter()
        browser.element(
            by.xpath(f'//table//tr[td[contains(normalize-space(), "{registro["empresa"]}")]]')
        ).should(be.clickable).click()
        print("Processo do campo EMPRESA concluído")
        time.sleep(3)

        # ============================
        # Estabelecimento
        # ============================
        print("CHECKPOINT 4 - Estabelecimento")
        lupa_estabelecimento = browser.element(
            'button[data-target="#modal_zoom_estabelecimento_medicao_1"]'
        ).should(be.present)
        browser.driver.execute_script("arguments[0].scrollIntoView(true);", lupa_estabelecimento())
        browser.driver.execute_script("arguments[0].click();", lupa_estabelecimento())
        time.sleep(2)
        browser.element('#tabela_zoom_estabelecimento_medicao_1_wrapper').should(be.visible)
        campo_busca = browser.element(
            '#tabela_zoom_estabelecimento_medicao_1_wrapper input.form-control[placeholder="Procurar"]'
        )
        campo_busca.should(be.visible).type(registro['empresa']).press_enter()
        time.sleep(2)
        browser.element(
            by.xpath(
                f'//table[@id="tabela_zoom_estabelecimento_medicao_1"]//td[normalize-space()="{registro["empresa"]}"]'
            )
        ).should(be.clickable).click()
        print("Processo do campo ESTABELECIMENTO concluído")
        time.sleep(3)

        # ============================
        # Fornecedor (com tratamento de erro)
        # ============================
        print("CHECKPOINT 5 - Fornecedor")
        lupa_fornecedor = browser.element(
            'button[data-target="#modal_zoom_fornecedor_medicao_1"]'
        ).should(be.present)
        browser.driver.execute_script("arguments[0].scrollIntoView(true);", lupa_fornecedor())
        browser.driver.execute_script("arguments[0].click();", lupa_fornecedor())
        time.sleep(2)

        # Garante que o modal abriu
        browser.element('#modal_zoom_fornecedor_medicao_1').should(be.visible)

        texto_fornecedor = str(registro['fornecedor']).strip()
        print(f"🔎 Procurando fornecedor: '{texto_fornecedor}'")

        # Campo de busca dentro do modal
        campo_busca_fornecedor = browser.element(
            '#tabela_zoom_fornecedor_medicao_1_wrapper input.form-control[placeholder="Procurar"]'
        )
        campo_busca_fornecedor.should(be.visible).clear().type(texto_fornecedor).press_enter()

        try:
            # tenta achar exatamente a linha do fornecedor da planilha
            linha_fornecedor = browser.element(
                by.xpath(
                    f'//*[@id="tabela_zoom_fornecedor_medicao_1"]//tbody/tr[td[contains(normalize-space(), "{texto_fornecedor}")]]'
                )
            ).should(be.clickable)

            print("Linha de fornecedor encontrada:", linha_fornecedor().text)
            linha_fornecedor.click()
            print("Processo do campo FORNECEDOR concluído")
            time.sleep(1)

        except TimeoutException:
            # não achou o fornecedor certo: NÃO seleciona outro!
            print(f"⚠️ Fornecedor '{texto_fornecedor}' não encontrado na tabela para o registro {indice_registro}.")
            print("   → Esse registro será PULADO para não selecionar fornecedor incorreto.")
            # sai do iframe e vai pro próximo registro
            browser.driver.switch_to.default_content()
            time.sleep(2)
            continue


        # ============================
        # Contrato
        # ============================
        print("CHECKPOINT 6 - Contrato")
        lupa_contrato = browser.element(
            'button[data-target="#modal_zoom_contrato_medicao_1"]'
        ).should(be.present)

        browser.driver.execute_script("arguments[0].scrollIntoView(true);", lupa_contrato())
        browser.driver.execute_script("arguments[0].click();", lupa_contrato())
        time.sleep(2)
        print("Abrindo modal de contrato...")

        browser.element('#modal_zoom_contrato_medicao_1').should(be.visible)
        time.sleep(1)

        try:
            campo_busca_contrato = browser.element(
                '#tabela_zoom_contrato_medicao_1_wrapper input.form-control[placeholder="Procurar"]'
            ).should(be.visible)
        except Exception:
            campo_busca_contrato = browser.element(
                '#modal_zoom_contrato_medicao_1 input.form-control[placeholder="Procurar"]'
            ).should(be.visible)

        numero_contrato = str(registro['contrato'])
        campo_busca_contrato.clear().type(numero_contrato)

        try:
            botao_buscar_contrato = browser.element(
                '#modal_zoom_contrato_medicao_1 button.btn.btn-primary'
            )
            if botao_buscar_contrato.matching(be.clickable):
                botao_buscar_contrato.click()
            else:
                campo_busca_contrato.press_enter()
        except Exception:
            campo_busca_contrato.press_enter()

        linha_contrato = browser.element(
            '#tabela_zoom_contrato_medicao_1 tbody tr'
        ).should(be.clickable)

        print("Linha de contrato encontrada:", linha_contrato().text)
        linha_contrato.click()
        print("Processo do campo CONTRATO concluído")
        time.sleep(2)

        print("CHECKPOINT 7 - Campos de datas e valores")

        # Datas normais
        preencher_campo('#id_data_inicio', registro['data_inicio'])
        time.sleep(3)
        preencher_campo('#id_data_fim', registro['data_fim'])
        time.sleep(3)
        # Competência com máscara mm/aaaa
        preencher_competencia('#id_competencia', registro['competencia'])
        time.sleep(3)
        preencher_campo('#id_data_emissao', registro['emissao_nf'])
        time.sleep(3)
        preencher_campo('#id_data_vencimento', registro['vencimento_nf'])
        time.sleep(3)
        preencher_campo('#id_nf_medicao', registro['id_nf'])
        time.sleep(3)

        print("Processo dos campos datas e valores concluídos")

        # ============================
        # VALOR DOS ITENS DO CONTRATO
        # ============================
        print("CHECKPOINT 8 - Itens do contrato")

        def preencher_valores_itens(indice_item_zero_based: int, valor_item):
            campos_valor = browser.all('div[class^="linha_valor_"] input.form-control.input-blueez')

            if not campos_valor:
                print("⚠️ Nenhum campo de valor de item foi encontrado na tela.")
                return

            total_itens = len(campos_valor)
            print(f"🧾 Foram encontrados {total_itens} itens de contrato na tela.")

            if indice_item_zero_based < 0 or indice_item_zero_based >= total_itens:
                print(f"⚠️ Índice de item inválido: {indice_item_zero_based}. "
                      f"Existe(m) apenas {total_itens} item(ns) na tela.")
                return

            for i, campo in enumerate(campos_valor):
                campo_real = campo.should(be.present)
                browser.driver.execute_script("arguments[0].scrollIntoView(true);", campo_real())

                valor = str(valor_item) if i == indice_item_zero_based else "0"

                browser.driver.execute_script("""
                    const campo = arguments[0];
                    campo.value = arguments[1];
                    campo.dispatchEvent(new Event('input', { bubbles: true }));
                    campo.dispatchEvent(new Event('change', { bubbles: true }));
                """, campo_real(), valor)

                print(f"   → Item {i+1}: valor definido para {valor}")

            print(f"✅ Processo dos campos de valor concluído. "
                  f"Item {indice_item_zero_based + 1} recebeu o valor {valor_item}, "
                  f"os demais ficaram com 0.")
            time.sleep(3)

        indice_item_planilha = int(registro['item_medido'])
        indice_zero_based = indice_item_planilha - 1
        preencher_valores_itens(indice_zero_based, registro['valor_item'])

        # Observações
        print("CHECKPOINT 9 - Observações")
        campo_obs = browser.element('#id_observacao_medicao').should(be.visible)
        browser.driver.execute_script("arguments[0].scrollIntoView(true);", campo_obs())
        campo_obs.clear()
        campo_obs.type(registro['observacao'])
        print("Processo do campo Observações concluído")
        time.sleep(3)

        # ============================
        # ====== Anexos (OPCIONAL) ===
        # ============================

        print("CHECKPOINT 10 - Anexos (opcional)")
        nomes_brutos = [registro.get('arquivo_1'), registro.get('arquivo_2')]

        nomes_validos = [
            nome.strip()
            for nome in nomes_brutos
            if isinstance(nome, str) and nome.strip()
        ]

        if not nomes_validos:
            print("ℹ️ Nenhum arquivo informado na planilha. Seguindo sem anexos.")
        else:
            print("📎 Arquivos informados na planilha:", nomes_validos)

            aba_anexos = browser.element('a[href="#content_tab_1_50"]').should(be.present)
            browser.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", aba_anexos())
            browser.driver.execute_script("arguments[0].click();", aba_anexos())
            browser.element('.modal.show, div[id*="anexo"], #modal_anexo_medicao_1').should(be.visible)
            print("Processo do campo Anexo concluído")
            time.sleep(2)

            botao_novo = browser.element('button.btn-orange-componente').should(be.clickable)
            browser.driver.execute_script("arguments[0].click();", botao_novo())
            browser.element('.modal.show, div[id*="anexo"], input[type=\"file\"]').should(be.visible)
            time.sleep(1)

            BASE_DIR = os.path.dirname(os.path.abspath(__file__))
            PASTA_ENTRADA = os.path.join(BASE_DIR, "entrada")

            def normaliza_nome(s: str) -> str:
                return "".join(c for c in s.lower() if c.isalnum())

            arquivos_encontrados = []

            for nome_raw in nomes_validos:
                parte_principal = nome_raw.split()[0]
                parte_sem_ext = parte_principal.split('.')[0]

                print(f"🔎 Procurando arquivo para a referência da planilha: '{nome_raw}'")

                caminho_exato = os.path.join(PASTA_ENTRADA, nome_raw)
                if os.path.exists(caminho_exato):
                    print(f"✅ Arquivo encontrado (nome exato): {caminho_exato}")
                    arquivos_encontrados.append(caminho_exato)
                    continue

                caminho_pdf = os.path.join(PASTA_ENTRADA, parte_sem_ext + ".pdf")
                if os.path.exists(caminho_pdf):
                    print(f"✅ Arquivo encontrado (forçando .pdf): {caminho_pdf}")
                    arquivos_encontrados.append(caminho_pdf)
                    continue

                chave_norm = normaliza_nome(parte_sem_ext)
                candidatos = []

                for raiz, pastas, arquivos in os.walk(PASTA_ENTRADA):
                    for arquivo in arquivos:
                        nome_arquivo_sem_ext = os.path.splitext(arquivo)[0]
                        arquivo_norm = normaliza_nome(nome_arquivo_sem_ext)
                        if chave_norm and chave_norm in arquivo_norm:
                            candidatos.append(os.path.join(raiz, arquivo))

                if len(candidatos) == 1:
                    print(f"✅ Arquivo encontrado (busca aproximada): {candidatos[0]}")
                    arquivos_encontrados.append(candidatos[0])
                elif len(candidatos) > 1:
                    print(f"⚠️ Vários arquivos encontrados para '{nome_raw}':")
                    for c in candidatos:
                        print("   -", c)
                else:
                    print(f"⚠️ Nenhum arquivo encontrado em 'entrada' para: {nome_raw}")

            if not arquivos_encontrados:
                print("⚠️ Nenhum arquivo válido encontrado para upload. Seguindo sem anexos.")
            else:
                pasta_temp = r"C:\Temp"
                os.makedirs(pasta_temp, exist_ok=True)

                arquivos_locais = []
                for origem in arquivos_encontrados:
                    destino = os.path.join(pasta_temp, os.path.basename(origem))
                    try:
                        shutil.copy2(origem, destino)
                        arquivos_locais.append(destino)
                    except Exception as e:
                        print(f"⚠️ Erro ao copiar {origem} → {destino}: {e}")

                if arquivos_locais:
                    print("✅ Arquivos copiados para:", arquivos_locais)

                    campo_upload = browser.element('#upload-file').should(be.present)
                    campo_upload.send_keys("\n".join(arquivos_locais))
                    time.sleep(3)

                    for arquivo in arquivos_locais:
                        try:
                            os.remove(arquivo)
                            print(f"🗑️ Arquivo temporário excluído: {arquivo}")
                        except Exception as e:
                            print(f"⚠️ Não foi possível excluir {arquivo}: {e}")

                    botao_enviar = browser.element('button.btn-upload-files').should(be.clickable)
                    browser.driver.execute_script("arguments[0].click();", botao_enviar())

                    browser.element('#upload-file').should(be.not_.visible)
                    time.sleep(3)
                else:
                    print("⚠️ Nenhum arquivo foi copiado com sucesso. Seguindo sem anexos.")

        # ============================
        # ====== Upload (ALTERADO) ===
        # ============================

        print("CHECKPOINT 11 - Upload complementar (arquivo_1/2)")

        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        PASTA_ENTRADA = os.path.join(BASE_DIR, "entrada")

        def normaliza_nome(s: str) -> str:
            return "".join(c for c in s.lower() if c.isalnum())

        nomes_arquivos_planilha = [registro.get('arquivo_1'), registro.get('arquivo_2')]
        arquivos_encontrados = []

        for nome in nomes_arquivos_planilha:
            if not isinstance(nome, str) or not nome.strip():
                print("⚠️ Nome de arquivo vazio ou inválido na planilha.")
                continue

            nome_raw = nome.strip()
            parte_principal = nome_raw.split()[0]
            parte_sem_ext = parte_principal.split('.')[0]

            print(f"🔎 Procurando arquivo para a referência da planilha: '{nome_raw}'")

            caminho_exato = os.path.join(PASTA_ENTRADA, nome_raw)
            if os.path.exists(caminho_exato):
                print(f"✅ Arquivo encontrado (nome exato): {caminho_exato}")
                arquivos_encontrados.append(caminho_exato)
                continue

            caminho_pdf = os.path.join(PASTA_ENTRADA, parte_sem_ext + ".pdf")
            if os.path.exists(caminho_pdf):
                print(f"✅ Arquivo encontrado (forçando .pdf): {caminho_pdf}")
                arquivos_encontrados.append(caminho_pdf)
                continue

            chave_norm = normaliza_nome(parte_sem_ext)
            candidatos = []

            for raiz, pastas, arquivos in os.walk(PASTA_ENTRADA):
                for arquivo in arquivos:
                    nome_arquivo_sem_ext = os.path.splitext(arquivo)[0]
                    arquivo_norm = normaliza_nome(nome_arquivo_sem_ext)
                    if chave_norm and chave_norm in arquivo_norm:
                        candidatos.append(os.path.join(raiz, arquivo))

            if len(candidatos) == 1:
                print(f"✅ Arquivo encontrado (busca aproximada): {candidatos[0]}")
                arquivos_encontrados.append(candidatos[0])
            elif len(candidatos) > 1:
                print(f"⚠️ Vários arquivos encontrados para '{nome_raw}':")
                for c in candidatos:
                    print("   -", c)
            else:
                print(f"⚠️ Nenhum arquivo encontrado na pasta 'entrada' para a referência: {nome_raw}")

        if not arquivos_encontrados:
            print("⚠️ Nenhum arquivo válido encontrado na pasta 'entrada'. Verifique a planilha e os arquivos.")
        else:
            pasta_temp = r"C:\Temp"
            os.makedirs(pasta_temp, exist_ok=True)

            arquivos_locais = []
            for origem in arquivos_encontrados:
                destino = os.path.join(pasta_temp, os.path.basename(origem))
                try:
                    shutil.copy2(origem, destino)
                    arquivos_locais.append(destino)
                except Exception as e:
                    print(f"⚠️ Erro ao copiar {origem} → {destino}: {e}")

            if arquivos_locais:
                print("✅ Arquivos copiados para:", arquivos_locais)

                campo_upload = browser.element('#upload-file').should(be.present)
                campo_upload.send_keys("\n".join(arquivos_locais))
                time.sleep(3)

                for arquivo in arquivos_locais:
                    try:
                        os.remove(arquivo)
                        print(f"🗑️ Arquivo temporário excluído: {arquivo}")
                    except Exception as e:
                        print(f"⚠️ Não foi possível excluir {arquivo}: {e}")

                botao_enviar = browser.element('button.btn-upload-files').should(be.clickable)
                browser.driver.execute_script("arguments[0].click();", botao_enviar())

                browser.element('#upload-file').should(be.not_.visible)
                time.sleep(3)
            else:
                print("⚠️ Nenhum arquivo foi copiado com sucesso. Verifique os nomes na planilha e os arquivos na pasta 'entrada'.")

        # ====== Botão Final ======
        print("CHECKPOINT 12 - Botão final Enviar")
        botao_enviar_solicitacao_0 = browser.element('#botao_enviar_solicitacao_0').should(be.present)
        browser.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", botao_enviar_solicitacao_0())

        if botao_enviar_solicitacao_0.matching(be.visible) and botao_enviar_solicitacao_0.matching(be.enabled):
            print("✅ Botão 'Enviar' localizado e pronto para clique.")
            # se um dia quiser realmente enviar:
            #browser.driver.execute_script("arguments[0].click();", botao_final_enviar())
            #browser.driver.execute_script("arguments[0].click();", botao_enviar_solicitacao_0())
        else:
            print("⚠️ Botão 'Enviar' não está visível ou disponível no momento.")
            print("✅ Teste de validação final concluído com segurança — sem enviar a solicitação.")

        # se chegou até aqui, consideramos esse registro OK
        resultado["mensagem"] = "Processado com sucesso"

        # volta para o conteúdo principal para o próximo registro
        browser.driver.switch_to.default_content()
        time.sleep(2)

    except Exception as e:
        import traceback
        print(f"\n❌ ERRO no registro {indice_registro}: {e}")
        traceback.print_exc()

        resultado["mensagem"] = str(e)

    finally:
        # garante volta ao conteúdo principal pro próximo loop
        try:
            browser.driver.switch_to.default_content()
        except Exception:
            pass
        time.sleep(2)

        # adiciona o resultado desse registro na lista geral
        RESULTADOS.append(resultado)

print("\n🎉 Processamento de todos os registros da planilha concluído.")

# ============================
# Gera o CSV de saída com status
# ============================
if RESULTADOS:
    df_resultados = pd.DataFrame(RESULTADOS)

    nome_arquivo = f"resultado_medicoes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    caminho_csv = os.path.join(PASTA_SAIDA, nome_arquivo)

    # usa ; como separador (muito comum em PT-BR) e utf-8-sig pra abrir bem no Excel
    df_resultados.to_csv(caminho_csv, index=False, sep=';', encoding='utf-8-sig')

    print(f"💾 Arquivo de saída gerado em: {caminho_csv}")
else:
    print("⚠️ Nenhum resultado para salvar no CSV.")
