# Imagem base do Python (Linux)
FROM python:3.12-slim

# Evita criar .pyc e força logs sem buffer
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Diretório de trabalho dentro do container
WORKDIR /app

# Instalar dependências de sistema (para psutil e etc.)
RUN apt-get update && apt-get install -y \
    build-essential \
 && rm -rf /var/lib/apt/lists/*

# Copia os requisitos e instala as libs Python
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copia TODO o código do projeto
COPY . /app/

# Expõe a porta 8000 (a mesma que o Django usa)
EXPOSE 8000

# Comando padrão: rodar o servidor Django escutando em 0.0.0.0
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
