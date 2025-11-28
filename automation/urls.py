from django.urls import path

from .views import (
    AutomationJobListView,
    AutomationJobCreateView,
    AutomationJobUpdateView,
    AutomationRunListView,
    AutomationJobRunListView,  # 👈 NOVO
    JobFilesView,  
    run_job_now,
)

app_name = "automation"

urlpatterns = [
    path("", AutomationJobListView.as_view(), name="job_list"),
    path("jobs/new/", AutomationJobCreateView.as_view(), name="job_create"),
    path("jobs/<int:pk>/edit/", AutomationJobUpdateView.as_view(), name="job_update"),
    path("jobs/<int:pk>/run/", run_job_now, name="job_run_now"),

    # 👇 Histórico de UM job específico
    path("jobs/<int:pk>/runs/", AutomationJobRunListView.as_view(), name="job_runs"),

    # Histórico geral de todas as execuções (já existia)
    path("runs/", AutomationRunListView.as_view(), name="run_list"),

    # 👇 NOVA ROTA PARA ARQUIVOS
    path("jobs/<int:pk>/files/", JobFilesView.as_view(), name="job_files"),
]
