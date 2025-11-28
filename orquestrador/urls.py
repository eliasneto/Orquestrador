from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

urlpatterns = [
    path("admin/", admin.site.urls),

    # Páginas HTML
    path("accounts/", include("accounts.urls")),

    # Home do sistema (Menu)
    path("", include("core.urls")),  # 👈 raiz "/"

    # API de autenticação (JWT)
    path("api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

        # 👇 Novo módulo de automação
    path("automation/", include("automation.urls")),

    # Novo módulo de monitoramento
    path("monitorServer/", include("monitorServer.urls")),

    # API de contas (ex.: /api/accounts/me/)
    path("api/accounts/", include("accounts.api_urls")),
]
