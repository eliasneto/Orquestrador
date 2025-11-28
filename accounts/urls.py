# accounts/urls.py
from django.urls import path
from .views import MyLoginView, my_logout_view

app_name = "accounts"

urlpatterns = [
    path("login/", MyLoginView.as_view(), name="login"),
    path("logout/", my_logout_view, name="logout"),
]
