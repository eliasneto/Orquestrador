from django.urls import path

from .views import (
    AutomationJobListView,
    AutomationJobCreateView,
    AutomationJobUpdateView,
    AutomationRunListView,
    AutomationJobRunListView,  # 👈 NOVO
    JobFileDownloadView,   # 👈 novo
    AutomationJobPauseView,
    AutomationJobResumeView,
    JobFilesView,  
    run_job_now,
    stop_job,
    AutomationEventListView, 
)

app_name = "automation"

urlpatterns = [
    path("", AutomationJobListView.as_view(), name="job_list"),
    path("jobs/<int:pk>/files/download/", JobFileDownloadView.as_view(), name="job_file_download"), #Download de arquivos
    path("jobs/new/", AutomationJobCreateView.as_view(), name="job_create"),
    path("jobs/<int:pk>/edit/", AutomationJobUpdateView.as_view(), name="job_update"),
    path("jobs/<int:pk>/run/", run_job_now, name="job_run_now"),
    path("jobs/<int:pk>/stop/", stop_job, name="job_stop"),  # 👈 NOVO

    path("jobs/<int:pk>/pause/", AutomationJobPauseView.as_view(), name="job_pause"), #Pausa Automação
    path("jobs/<int:pk>/resume/", AutomationJobResumeView.as_view(), name="job_resume"), #retira pausa Automação

    # 👇 Histórico de UM job específico
    path("jobs/<int:pk>/runs/", AutomationJobRunListView.as_view(), name="job_runs"),

    # Histórico geral de todas as execuções (já existia)
    path("runs/", AutomationRunListView.as_view(), name="run_list"),

    # 👇 NOVA ROTA PARA ARQUIVOS
    path("jobs/<int:pk>/files/", JobFilesView.as_view(), name="job_files"),

    # 👇 NOVO: lista geral de eventos do orquestrador
    path("events/", AutomationEventListView.as_view(), name="event_list"),
]
