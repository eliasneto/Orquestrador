import requests
import smtplib
import pyodbc
import os
import json
from email.message import EmailMessage
from datetime import datetime

# =================================================================================
# CONFIGURAÇÕES
# =================================================================================

# 1. Lista de sites que você deseja monitorar
SITES_PARA_VERIFICAR = [
    "https://perfuratrizesdobrasil.com.br/",
    "https://www.howbe.com.br/",
    "https://www.bayinvest.com.br/",
    "https://www.lktec.com.br/",
    "https://www.studpb.com.br/",
    "https://www.2money.com.br/",
    "https://acessoseguro.sme.fortaleza.ce.gov.br/#/",
    "https://sefin.caucaia.ce.gov.br/",
    "https://megainfraestrutura.com.br/app/login",
    "https://speedcsc.com.br/",
    "https://empresa.nibo.com.br/Schedule/Out/261ab173-09cd-4140-8f79-4d2ea6391ba0",
    "https://howbetec.sharepoint.com/sites/intranet",
    "https://192.168.90.50/ui/#/login",
    "https://192.168.90.49/ui/#/login",
    "https://192.168.90.48/ui/#/login"
]

# 2. Configurações do Banco de Dados SQL Server
DB_CONFIG = {
    'driver': '{ODBC Driver 17 for SQL Server}',
    'server': '192.168.17.100',
    'database': 'howbe',
    'username': 'SA',
    'password': os.getenv('DB_PASS', 'teste@56')
}

# 3. Configurações de E-mail (SMTP - Office 365) para o relatório final
EMAIL_CONFIG = {
    'smtp_server': 'smtp.office365.com',
    'smtp_port': 587,
    'remetente': 'sistemas@howbe.com.br',
    'senha': os.getenv('EMAIL_PASS', 'SapHowbe2025'), # Exemplo usando variável de ambiente
    'destinatario': 'ti@speedcsc.com.br'
}

# 4. Configurações do Telegram para o relatório final
TELEGRAM_CONFIG = {
    'bot_token': os.getenv('TELEGRAM_TOKEN', '7835728705:AAFtk1rueiDJNe_ORlkpLP6qBKpYQnNKI4M'), # Insira seu Token aqui ou use variável de ambiente
    'chat_id': os.getenv('TELEGRAM_CHAT_ID', '-1002376779037')   # Insira o Chat ID do grupo aqui
}

# 5. Arquivo para armazenar o último estado dos sites
ARQUIVO_ESTADO = 'status_anterior.json'

# ==============================================================================
# FUNÇÕES AUXILIARES
# ==============================================================================

def carregar_estado_anterior():
    """Lê o arquivo JSON para obter o último estado conhecido dos sites."""
    try:
        with open(ARQUIVO_ESTADO, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def salvar_estado_atual(estado):
    """Salva o estado atual dos sites no arquivo JSON."""
    with open(ARQUIVO_ESTADO, 'w') as f:
        json.dump(estado, f, indent=4)

def registrar_log_no_banco(url, status, detalhes):
    """Registra o log de status no banco de dados."""
    try:
        conn_str = (f"DRIVER={DB_CONFIG['driver']};SERVER={DB_CONFIG['server']};DATABASE={DB_CONFIG['database']};UID={DB_CONFIG['username']};PWD={DB_CONFIG['password']};TrustServerCertificate=yes;")
        with pyodbc.connect(conn_str, timeout=10) as conn:
            cursor = conn.cursor()
            sql = "INSERT INTO dbo.sites (url_site, status_erro, detalhes_erro, data_hora_registro) VALUES (?, ?, ?, ?);"
            agora = datetime.now()
            detalhes_truncados = (detalhes[:497] + '...') if len(detalhes) > 500 else detalhes
            cursor.execute(sql, url, status, detalhes_truncados, agora)
            conn.commit()
            print(f"INFO: Status '{status}' do site '{url}' registrado no banco.")
    except pyodbc.Error as ex:
        print(f"--- ERRO DE BANCO DE DADOS ---\nNão foi possível registrar o log para: {url}.\nDetalhes: {ex}\n-----------------------------")

def enviar_relatorio_consolidado(sites_ok, sites_com_erro, sites_que_mudaram, motivo):
    """Envia relatórios por e-mail e Telegram com base no motivo."""
    print(f"\nINFO: Preparando para enviar relatórios. Motivo: {motivo}")
    enviar_relatorio_email(sites_ok, sites_com_erro, sites_que_mudaram, motivo)
    enviar_relatorio_telegram(sites_ok, sites_com_erro, sites_que_mudaram, motivo)

def enviar_relatorio_email(sites_ok, sites_com_erro, sites_que_mudaram, motivo):
    """Formata e envia um relatório por e-mail com base no motivo (MUDANÇA ou DIÁRIO)."""
    if not EMAIL_CONFIG['senha']:
        print("AVISO: E-mail não configurado.")
        return

    timestamp = datetime.now().strftime('%d/%m/%Y às %H:%M:%S')
    
    if motivo == "MUDANÇA":
        assunto = f"ALERTA: {len(sites_que_mudaram)} Mudança(s) de Status de Sites"
        titulo_principal = "&#10071; Alerta: Mudanças de Status Detectadas"
    else: # motivo == "DIÁRIO"
        assunto = "Relatório Diário de Status de Sites"
        titulo_principal = "&#128197; Relatório Diário Completo"

    # Monta o corpo do e-mail
    html = f"""
    <html><head><style>body{{font-family:sans-serif;}}table{{border-collapse:collapse;width:100%;}}th,td{{border:1px solid #ddd;text-align:left;padding:8px;}}th{{background-color:#f2f2f2;}}.status-ok{{background-color:#d4edda;}}.status-falha{{background-color:#f8d7da;}}.mudanca{{background-color:#fff3cd;}}</style></head>
    <body><h2>&#128276; Relatório de Monitoramento de Sites</h2>
    <p><strong>Verificação realizada em:</strong> {timestamp}</p>
    <h3>{titulo_principal}</h3>
    """

    if motivo == "MUDANÇA":
        html += "<table><tr><th>URL</th><th>Status Anterior</th><th>Status Novo</th></tr>"
        for url, status_anterior, status_novo in sites_que_mudaram:
            html += f"""<tr class="mudanca"><td>{url}</td><td>{status_anterior or 'N/A'}</td><td><b>{status_novo}</b></td></tr>"""
        html += "</table><h3>&#128221; Resumo Completo Atual</h3>"

    # Tabela completa (sempre incluída)
    html += "<table><tr><th>Status</th><th>URL</th><th>Detalhes</th></tr>"
    for url, status, detalhes in sites_com_erro:
        html += f"""<tr class="status-falha"><td><b>&#10060; FALHA</b></td><td>{url}</td><td><b>{status}</b> - {detalhes}</td></tr>"""
    for url, status_code, is_sharepoint in sites_ok:
        detalhe_ok = "Site respondeu, mas acesso completo pode requerer login." if is_sharepoint else "Site online e acessível."
        html += f"""<tr class="status-ok"><td>&#9989; OK</td><td>{url}</td><td>[Status {status_code}] {detalhe_ok}</td></tr>"""
    html += "</table></body></html>"
    
    try:
        msg = EmailMessage()
        msg['Subject'] = assunto
        msg['From'] = EMAIL_CONFIG['remetente']
        msg['To'] = EMAIL_CONFIG['destinatario']
        msg.add_alternative(html, subtype='html')
        with smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port']) as smtp:
            smtp.starttls()
            smtp.login(EMAIL_CONFIG['remetente'], EMAIL_CONFIG['senha'])
            smtp.send_message(msg)
        print("INFO: Relatório por e-mail enviado com sucesso.")
    except Exception as e:
        print(f"--- ERRO DE E-MAIL ---\nNão foi possível enviar o relatório.\nDetalhes: {e}\n----------------------")

def enviar_relatorio_telegram(sites_ok, sites_com_erro, sites_que_mudaram, motivo):
    """Formata e envia relatório para o Telegram com base no motivo."""
    token, chat_id = TELEGRAM_CONFIG['bot_token'], TELEGRAM_CONFIG['chat_id']
    if not token or not chat_id:
        print("AVISO: Telegram não configurado.")
        return
        
    timestamp = datetime.now().strftime('%d/%m/%Y às %H:%M:%S')
    mensagem = [f"*\U0001F4DD Relatório de Monitoramento de Sites*\n_{timestamp}_"]
    
    if motivo == "MUDANÇA":
        mensagem.append(f"\n*\U00002757 ALERTA: MUDANÇAS DE STATUS DETECTADAS ({len(sites_que_mudaram)})*")
        for url, status_anterior, status_novo in sites_que_mudaram:
            site_curto = url.split('//')[1].split('/')[0]
            mensagem.append(f"`{site_curto}`\n_{status_anterior or 'N/A'}_ \u27A1\uFE0F *{status_novo}*")
        mensagem.append(f"\n*\U0001F4CB RESUMO COMPLETO ATUAL*")
    else: # motivo == "DIÁRIO"
        mensagem.append(f"\n*\U0001F4C6 RELATÓRIO DIÁRIO COMPLETO*")

    # Resumo (sempre incluído)
    if sites_ok: mensagem.append(f"\n*\U00002705 SITES OK ({len(sites_ok)})*")
    if sites_com_erro: mensagem.append(f"\n*\U0000274C SITES COM FALHA ({len(sites_com_erro)})*")

    texto_final = "\n".join(mensagem)
    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {'chat_id': chat_id, 'text': texto_final, 'parse_mode': 'Markdown'}
    try:
        response = requests.post(api_url, data=payload, timeout=10)
        if response.status_code == 200:
            print("INFO: Relatório para o Telegram enviado com sucesso.")
        else:
            print(f"--- ERRO NO TELEGRAM ---\nFalha ao enviar. Status: {response.status_code}\nResposta: {response.text}\n------------------------")
    except Exception as e:
        print(f"--- ERRO NO TELEGRAM ---\nNão foi possível conectar à API.\nDetalhes: {e}\n------------------------")

# ==============================================================================
# LÓGICA PRINCIPAL
# ==============================================================================

def monitorar_sites():
    """Verifica os sites, notificando sobre mudanças ou enviando um relatório diário."""
    agora = datetime.now()
    hora_atual = agora.hour
    print("="*60 + f"\nIniciando verificação... {agora.strftime('%d/%m/%Y %H:%M:%S')}\n" + "="*60)
    
    estado_anterior = carregar_estado_anterior()
    estado_atual = {}
    sites_ok, sites_com_erro, sites_que_mudaram = [], [], []

    requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

    for url in SITES_PARA_VERIFICAR:
        status_atual_texto, detalhes = None, "Site online e acessível."
        try:
            verificar_ssl = not ("192.168." in url)
            response = requests.get(url, headers=headers, timeout=15, verify=verificar_ssl, allow_redirects=True)
            if 200 <= response.status_code < 300:
                status_atual_texto = f"OK {response.status_code}"
                sites_ok.append((url, response.status_code, "sharepoint.com" in url))
            else:
                status_atual_texto = f"Erro HTTP {response.status_code}"
                detalhes = f"O site respondeu com o código: {response.status_code}"
        except requests.exceptions.SSLError:
            status_atual_texto, detalhes = "Certificado SSL Inválido", "O certificado não é válido ou confiável."
        except requests.exceptions.ConnectionError:
            status_atual_texto, detalhes = "Offline / Erro de Conexão", "Não foi possível conectar."
        except requests.exceptions.Timeout:
            status_atual_texto, detalhes = "Timeout", "O site demorou muito para responder."
        except requests.exceptions.RequestException as e:
            status_atual_texto, detalhes = "Erro na Requisição", f"Erro inesperado: {e}"
        
        if "OK" not in status_atual_texto:
            sites_com_erro.append((url, status_atual_texto, detalhes))
        
        status_anterior_site = estado_anterior.get(url)
        if status_atual_texto != status_anterior_site:
            print(f"ALERTA: Mudança de status para '{url}': de '{status_anterior_site or 'Nenhum'}' para '{status_atual_texto}'")
            sites_que_mudaram.append((url, status_anterior_site, status_atual_texto))
        
        estado_atual[url] = status_atual_texto
        registrar_log_no_banco(url, status_atual_texto, detalhes)

    # --- DECISÃO DE NOTIFICAR ---
    is_horario_relatorio_diario = (7 <= hora_atual < 8)

    if sites_que_mudaram:
        enviar_relatorio_consolidado(sites_ok, sites_com_erro, sites_que_mudaram, motivo="MUDANÇA")
    elif is_horario_relatorio_diario:
        print("\nINFO: Horário do relatório diário. Enviando checklist completo.")
        enviar_relatorio_consolidado(sites_ok, sites_com_erro, sites_que_mudaram, motivo="DIÁRIO")
    else:
        print("\nINFO: Nenhuma mudança de status detectada e fora do horário do relatório diário. Nenhuma notificação será enviada.")

    salvar_estado_atual(estado_atual)
    print("\n" + "="*60 + "\nVerificação concluída.\n" + "="*60)

if __name__ == "__main__":
    monitorar_sites()
