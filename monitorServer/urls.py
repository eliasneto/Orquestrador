# monitor/urls.py
from django.urls import path
from .views import SystemHealthView, system_health_api, kill_process_api


app_name = "monitorServer"

urlpatterns = [
    path("", SystemHealthView.as_view(), name="system_health"),          # /monitor/
    path("api/system/", system_health_api, name="system_health_api"),    # /monitor/api/system/
    path("api/kill/", kill_process_api, name="kill_process_api"),       # /mata processo no front
]
