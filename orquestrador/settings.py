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

USE_AD_AUTH = os.getenv("USE_AD_AUTH", "false").lower() == "true"

# Se USE_SQLITE=true (ou não existir), usa SQLite.
# Se USE_SQLITE=false, usa MySQL.
USE_SQLITE = os.getenv("USE_SQLITE", "true").lower() == "false"

# ============================================
#  CONFIGURAÇÕES BÁSICAS DJANGO
# ============================================

SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-s286$^7)mne+j19y7=$&tjf2^hkv7*q)u#vq%w%mnw6u^y37+b",
)

DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"

ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    "192.168.18.35",
    "*",
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
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
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
#  BACKENDS DE AUTENTICAÇÃO (Django x AD)
# ============================================
if USE_AD_AUTH:
    AUTHENTICATION_BACKENDS = [
        "django_auth_ldap.backend.LDAPBackend",         # autentica no AD
        "django.contrib.auth.backends.ModelBackend",    # ainda permite superuser local
    ]
else:
    AUTHENTICATION_BACKENDS = [
        "django.contrib.auth.backends.ModelBackend",
    ]

# ============================================
#  CONFIG LDAP / AD (usa variáveis do .env)
# ============================================
if USE_AD_AUTH:
    import ldap
    from django_auth_ldap.config import LDAPSearch, ActiveDirectoryGroupType

    # Aceita tanto AD_SERVER quanto AD_SERVER_URI
    AUTH_LDAP_SERVER_URI = os.getenv("AD_SERVER") or os.getenv("AD_SERVER_URI", "")

    # Aceita tanto AD_USER quanto AD_BIND_DN
    AUTH_LDAP_BIND_DN = os.getenv("AD_USER") or os.getenv("AD_BIND_DN", "")
    AUTH_LDAP_BIND_PASSWORD = os.getenv("AD_PASS") or os.getenv("AD_BIND_PASSWORD", "")

    # Base DN (fallback pros nomes antigos se precisar)
    BASE_DN = os.getenv("BASE_DN") or os.getenv("AD_USER_SEARCH_BASE", "")

    # Onde buscar usuários
    AUTH_LDAP_USER_SEARCH = LDAPSearch(
        BASE_DN,
        ldap.SCOPE_SUBTREE,
        "(sAMAccountName=%(user)s)",   # login = samAccountName
    )

    # Onde buscar grupos
    GROUP_BASE_DN = os.getenv("AD_GROUP_SEARCH_BASE", BASE_DN)
    AUTH_LDAP_GROUP_SEARCH = LDAPSearch(
        GROUP_BASE_DN,
        ldap.SCOPE_SUBTREE,
        "(objectClass=group)",
    )
    AUTH_LDAP_GROUP_TYPE = ActiveDirectoryGroupType()

    # Mapear atributos do AD -> User do Django
    AUTH_LDAP_USER_ATTR_MAP = {
        "first_name": "givenName",
        "last_name": "sn",
        "email": "mail",
    }

    # Atualiza sempre que o usuário logar
    AUTH_LDAP_ALWAYS_UPDATE_USER = True

    # Espelhar grupos do AD em auth.Group
    AUTH_LDAP_MIRROR_GROUPS = True

    # Restringe login a um grupo específico do AD (opcional)
    grupo_permitido_dn = os.getenv("GRUPO_PERMITIDO", "")
    if grupo_permitido_dn:
        AUTH_LDAP_REQUIRE_GROUP = grupo_permitido_dn

    # Domínio padrão pra login tipo "elias.neto"
    AD_DEFAULT_DOMAIN = os.getenv("AD_DOMAIN") or os.getenv("AD_DEFAULT_DOMAIN", "")
    if AD_DEFAULT_DOMAIN:
        AUTH_LDAP_USER_DOMAIN = AD_DEFAULT_DOMAIN

    # Mesma opção que você usou no teste manual
    AUTH_LDAP_CONNECTION_OPTIONS = {
        ldap.OPT_REFERRALS: 0,
    }

# ============================================
#  INTERNACIONALIZAÇÃO
# ============================================
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Fortaleza"
USE_I18N = True
USE_TZ = True

# ============================================
#  STATIC FILES
# ============================================
STATIC_URL = "static/"

STATICFILES_DIRS = [
    BASE_DIR / "orquestrador" / "static",
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
AUTOMATIONS_WORKSPACE_ROOT = BASE_DIR / "automation_workspaces"

# ============================================
#  LOGIN / LOGOUT
# ============================================
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# Tempo da sessão em segundos (10 minutos)
SESSION_COOKIE_AGE = 10 * 60  # 10 minutos

# Renova o tempo de expiração a cada requisição do usuário
SESSION_SAVE_EVERY_REQUEST = True
