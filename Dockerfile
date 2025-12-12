# Imagem base
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DOCKERIZE_VERSION v0.6.1

# Define diretório de trabalho para /app (Padrão correto)
WORKDIR /app

# Instalação UNIFICADA (Sistema + Dockerize + Drivers MS SQL)
RUN apt-get update && apt-get install -y \
    build-essential \
    default-libmysqlclient-dev \
    pkg-config \
    libldap2-dev \
    libsasl2-dev \
    libssl-dev \
    wget \
    curl \
    gnupg2 \
    unixodbc \
    unixodbc-dev \
    # --- Instalação do Dockerize ---
    && wget https://github.com/jwilder/dockerize/releases/download/$DOCKERIZE_VERSION/dockerize-linux-amd64-$DOCKERIZE_VERSION.tar.gz \
    && tar -C /usr/local/bin -xzvf dockerize-linux-amd64-$DOCKERIZE_VERSION.tar.gz \
    && rm dockerize-linux-amd64-$DOCKERIZE_VERSION.tar.gz \
    # --- Instalação Driver MS SQL (Versão Debian 12/Bookworm Correta) ---
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && curl https://packages.microsoft.com/config/debian/12/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql17 \
    # --- Limpeza Final ---
    && rm -rf /var/lib/apt/lists/*

# Copia requirements e instala
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install mysqlclient && \
    pip install gunicorn

# Copia o código para /app
COPY . .

EXPOSE 8001

# Comando padrão
CMD ["gunicorn", "orquestrador.wsgi:application", "--bind", "0.0.0.0:8001"]