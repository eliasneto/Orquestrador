from django.conf import settings

def project_version(request):
    return {'VERSION': settings.VERSION}