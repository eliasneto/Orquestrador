# accounts/api_urls.py
from django.urls import path
from . import api_views

app_name = "accounts_api"

urlpatterns = [
    path("me/", api_views.me, name="me"),
]
