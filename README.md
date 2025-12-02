# Orquestrador – Ambiente Python/Django com Docker

Este projeto é uma aplicação Python (Django) que pode ser executada tanto **localmente (sem Docker)** quanto em um ambiente **containerizado com Docker e Docker Compose**.

---

## 🔧 Tecnologias utilizadas

- Python 3.11+
- Django
- Gunicorn (produção com Docker)
- Docker & Docker Compose
- (Opcional) PostgreSQL via Docker

---

## 🖥️ Ambiente local (sem Docker)

### 1. Pré-requisitos

- **Windows** instalado
- **Python 3.11+** instalado e disponível no `PATH`
- (Opcional) **Git**, se for clonar o projeto de um repositório

### 2. Criar e ativar ambiente virtual

No **Windows** (CMD ou PowerShell), dentro da pasta do projeto:

```bash
python -m venv .venv

### Ativar ambiente virtual
.\.venv\Scripts\activate

### Instalar dependencias
pip install -r requirements.txt

# Gera arquivo requirements.txt
pip freeze > requirements.txt

# Startar o servidor
python manage.py migrate
python manage.py runserver 0.0.0.0:8000