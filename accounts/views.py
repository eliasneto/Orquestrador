# accounts/views.py
from django.contrib.auth.views import LoginView
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse_lazy


class MyLoginView(LoginView):
    """
    View de login padrão do Django.

    - Usa o template accounts/login.html
    - Se o usuário já estiver autenticado, redireciona direto
      para a página definida em LOGIN_REDIRECT_URL (settings),
      que no seu caso é "/".
    """
    template_name = "accounts/login.html"
    redirect_authenticated_user = True  # mantém a regra que você quer


def my_logout_view(request):
    """
    Faz logout "na mão":

    - Chama django.contrib.auth.logout(request) para limpar a sessão
    - Depois redireciona o usuário para a tela de login

    Isso evita qualquer comportamento estranho do LogoutView e
    deixa claro o que está acontecendo.
    """
    logout(request)  # limpa as credenciais da sessão
    return redirect("accounts:login")  # volta para /accounts/login/
