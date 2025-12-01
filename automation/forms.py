# automation/forms.py
from django import forms
from .models import AutomationJob


class AutomationJobForm(forms.ModelForm):
    class Meta:
        model = AutomationJob
        fields = [
            "name",
            "description",
            "code",
            "sector",
            "external_main_script",
            "is_active",
            "allow_manual",
            "schedule_type",
            "one_off_run_at",
            "daily_time",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Ex: Robô IXC – Login Cliente"}
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Explique rapidamente o que essa automação faz.",
                }
            ),

                        # 👉 AQUI deixamos o Setor com cara de Bootstrap, igual aos outros
            "sector": forms.Select(
                attrs={
                    "class": "form-select",   # mesmo estilo do schedule_type
                }
            ),
            
            "code": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "robo_ixc_login_cliente"}
            ),
            "external_main_script": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "main.py"}
            ),
            "schedule_type": forms.Select(attrs={"class": "form-select"}),
            "one_off_run_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"}
            ),
            "daily_time": forms.TimeInput(
                attrs={"class": "form-control", "type": "time"}
            ),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "allow_manual": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


# ---------- Upload múltiplo de arquivos ----------

class MultiFileInput(forms.ClearableFileInput):
    # Diz pro widget que ele aceita múltiplos arquivos
    allow_multiple_selected = True


class MultiFileField(forms.Field):
    """
    Campo simples que recebe uma LISTA de arquivos.

    Não usa FileField justamente pra não dar o erro
    "No file was submitted..." quando vier uma lista.
    """

    widget = MultiFileInput

    def __init__(self, *args, **kwargs):
        # vamos tratar "nenhum arquivo" manualmente na view
        kwargs.setdefault("required", False)
        super().__init__(*args, **kwargs)

    def to_python(self, data):
        # o widget retorna uma lista (ou None)
        if not data:
            return []
        return data


class JobFileUploadForm(forms.Form):
    files = MultiFileField(
        label="Selecione um ou mais arquivos",
        widget=MultiFileInput(
            attrs={
                "class": "form-control",
            }
        ),
    )
