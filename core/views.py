# core/views.py
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin

class HomeView(LoginRequiredMixin, TemplateView):
    """
    Tela inicial do sistema (dashboard).
    Só acessa se estiver logado.
    """
    template_name = "core/home.html"
