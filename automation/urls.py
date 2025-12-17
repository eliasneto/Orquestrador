from django.urls import path

from .views import (
    AutomationJobListView,
    AutomationJobCreateView,
    AutomationJobUpdateView,
    AutomationRunListView,
    AutomationJobRunListView,
    JobFileDownloadView,
    AutomationJobPauseView,
    AutomationJobResumeView,
    JobFilesView,
    run_job_now,
    stop_job,
    AutomationEventListView,
    api_run_log,
    job_reset_venv,
    job_reset_folder,
    job_reset_workspace,
)

app_name = "automation"

urlpatterns = [
    path("", AutomationJobListView.as_view(), name="job_list"),

    path("jobs/new/", AutomationJobCreateView.as_view(), name="job_create"),
    path("jobs/<int:pk>/edit/", AutomationJobUpdateView.as_view(), name="job_update"),

    path("jobs/<int:pk>/run/", run_job_now, name="job_run_now"),
    path("jobs/<int:pk>/stop/", stop_job, name="job_stop"),

    path("jobs/<int:pk>/pause/", AutomationJobPauseView.as_view(), name="job_pause"),
    path("jobs/<int:pk>/resume/", AutomationJobResumeView.as_view(), name="job_resume"),

    path("jobs/<int:pk>/runs/", AutomationJobRunListView.as_view(), name="job_runs"),
    path("runs/", AutomationRunListView.as_view(), name="run_list"),

    path("jobs/<int:pk>/files/", JobFilesView.as_view(), name="job_files"),
    path("jobs/<int:pk>/files/download/", JobFileDownloadView.as_view(), name="job_file_download"),

    path("events/", AutomationEventListView.as_view(), name="event_list"),
    path("api/run/<int:pk>/log/", api_run_log, name="api_run_log"),

    path("jobs/<int:pk>/venv/reset/", job_reset_venv, name="job_reset_venv"),
    path("jobs/<int:pk>/workspace/reset/", job_reset_workspace, name="job_reset_workspace"),
    path("jobs/<int:pk>/folder/reset/", job_reset_folder, name="job_reset_folder"),
]
