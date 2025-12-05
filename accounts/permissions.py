# accounts/permissions.py
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.decorators import user_passes_test

ADMINISTRADOR = "Administrador_Orquestrador"  # nome do grupo no Django Admin


def user_is_admin(user):
    """
    Retorna True se o usuário for:
    - autenticado
    - superuser OU estiver no grupo 'Administrador'
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=ADMINISTRADOR).exists()


class AdminRequiredMixin(UserPassesTestMixin):
    """
    Mixin para CBVs que exigem que o usuário seja Administrador.
    Usa grupo 'Administrador' ou superuser.
    """

    login_url = "accounts:login"  # ajuste se o nome da sua url de login for outro
    raise_exception = True  # se não for admin, retorna 403 em vez de redirect

    def test_func(self):
        return user_is_admin(self.request.user)


def admin_required(view_func):
    """
    Decorator para FBVs que exigem que o usuário seja Administrador.
    """

    from functools import wraps
    from django.contrib.auth.views import redirect_to_login
    from django.core.exceptions import PermissionDenied

    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not user_is_admin(user):
            raise PermissionDenied  # retorna 403
        return view_func(request, *args, **kwargs)

    return _wrapped_view
