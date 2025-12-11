# Imagem base do Python
FROM python:3.12-slim

# Evita criar .pyc e deixa logs sem buffer
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Diretório de trabalho dentro do container
WORKDIR /app

# Instalar dependências do sistema para:
# - mysqlclient  (libmysqlclient + build-essential + pkg-config)
# - python-ldap  (libldap2-dev + libsasl2-dev + libssl-dev)
RUN apt-get update && apt-get install -y \
    build-essential \
    default-libmysqlclient-dev \
    pkg-config \
    libldap2-dev \
    libsasl2-dev \
    libssl-dev \
    wget \
    && rm -rf /var/lib/apt/lists/*

# NOVO PASSO: Instalar o Dockerize (Utilitário de Espera de Rede)
ENV DOCKERIZE_VERSION v0.6.1
RUN wget https://github.com/jwilder/dockerize/releases/download/$DOCKERIZE_VERSION/dockerize-linux-amd64-$DOCKERIZE_VERSION.tar.gz \
    && tar -C /usr/local/bin -xzvf dockerize-linux-amd64-$DOCKERIZE_VERSION.tar.gz \
    && rm dockerize-linux-amd64-$DOCKERIZE_VERSION.tar.gz
# Copia requirements e instala dependências Python do projeto principal
COPY requirements.txt /app/

RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copia o resto do código
COPY . /app/

# Expor porta 8000 (Django/Gunicorn)
EXPOSE 8001

# Comando padrão (pode ser sobrescrito no docker-compose)
CMD ["gunicorn", "orquestrador.wsgi:application", "--bind", "0.0.0.0:8001"]
