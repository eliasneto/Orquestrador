# Imagem base do Python
FROM python:3.12-slim

# Evita criar .pyc e deixa logs sem buffer
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Diretório de trabalho dentro do container
WORKDIR /app

# Instalar dependências do sistema para:
# - mysqlclient (já tinha)
# - pyodbc (unixodbc + unixodbc-dev)
RUN apt-get update && apt-get install -y \
    build-essential \
    default-libmysqlclient-dev \
    pkg-config \
    unixodbc \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

# Copia requirements e instala dependências Python do projeto principal
COPY requirements.txt /app/

RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copia o resto do código
COPY . /app/

# Expor porta 8000 (Django/Gunicorn)
EXPOSE 8000

# Comando padrão (pode ser sobrescrito no docker-compose)
CMD ["gunicorn", "orquestrador.wsgi:application", "--bind", "0.0.0.0:8000"]
