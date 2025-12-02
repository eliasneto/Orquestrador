from pathlib import Path
from datetime import timedelta
import os

from dotenv import load_dotenv  # pip install python-dotenv

# ============================================
#  PATHS BÁSICOS
# ============================================
BASE_DIR = Path(__file__).resolve().parent.parent

# ============================================
#  .ENV
# ============================================
load_dotenv()

# Se USE_SQLITE=true (ou não existir), usa SQLite.
# Se USE_SQLITE=false, usa MySQL.
USE_SQLITE = os.getenv("USE_SQLITE", "true").lower() == "true"

# ============================================
#  CONFIGURAÇÕES BÁSICAS DJANGO
# ============================================

# Em produção, ideal é pegar do .env:
# DJANGO_SECRET_KEY="chave_super_secreta"
SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-s286$^7)mne+j19y7=$&tjf2^hkv7*q)u#vq%w%mnw6u^y37+b",
)

# DEBUG: em produção, coloque DJANGO_DEBUG=false no .env
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"

ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    "192.168.18.35",
    # se quiser liberar geral em ambiente interno:
    # "*",
]

# ============================================
#  APPS
# ============================================
INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Terceiros
    "rest_framework",
    "rest_framework_simplejwt",

    # Seus apps
    "accounts",
    "core",
    "monitorServer",
    "automation",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "orquestrador.urls"

# ============================================
#  TEMPLATES
# ============================================
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Django vai procurar também em BASE_DIR / "templates"
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "orquestrador.wsgi.application"

# ============================================
#  DATABASES – SQLite x MySQL
# ============================================

if USE_SQLITE:
    # Desenvolvimento / testes (Windows, máquina local)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    # Produção / servidor com MySQL (requer mysqlclient instalado no ambiente)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.getenv("DB_NAME", "orquestrador"),
            "USER": os.getenv("DB_USER", "orquestrador"),
            "PASSWORD": os.getenv("DB_PASSWORD", "orquestrador"),
            "HOST": os.getenv("DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DB_PORT", "3306"),
            "OPTIONS": {
                "charset": "utf8mb4",
            },
        }
    }

# ============================================
#  AUTH / SENHAS
# ============================================
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# ============================================
#  INTERNACIONALIZAÇÃO
# ============================================

# Se quiser tudo em pt-BR:
LANGUAGE_CODE = "pt-br"

# Fuso de Fortaleza
TIME_ZONE = "America/Fortaleza"

USE_I18N = True
USE_TZ = True

# ============================================
#  STATIC FILES
# ============================================
STATIC_URL = "static/"

# (opcionais, mas já deixo prontos para ambiente real)
STATICFILES_DIRS = [
    BASE_DIR / "static",
]
STATIC_ROOT = BASE_DIR / "staticfiles"

# ============================================
#  PRIMARY KEY PADRÃO
# ============================================
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ============================================
#  DRF + JWT
# ============================================
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}

# ============================================
#  AUTOMAÇÕES – WORKSPACE
# ============================================
# Raiz onde ficarão as pastas das automações com venv
AUTOMATIONS_WORKSPACE_ROOT = BASE_DIR / "automation_workspaces"

# ============================================
#  LOGIN / LOGOUT
# ============================================
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"          # depois do login vai para "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"
