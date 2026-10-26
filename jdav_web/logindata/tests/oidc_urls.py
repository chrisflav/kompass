"""The project's URLs with the OIDC client's routes mounted whatever the config.

`SessionRefresh` resolves those routes by name, and they are only part of
``jdav_web.urls`` when OIDC is enabled.
"""

from django.urls import include
from django.urls import path

from jdav_web.urls import urlpatterns as project_urlpatterns

urlpatterns = project_urlpatterns + [path("oidc/", include("mozilla_django_oidc.urls"))]
