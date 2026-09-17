"""jdav_web URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.10/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""

from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.urls import include
from django.urls import path
from django.urls import re_path
from oauth2_provider import urls as oauth2_urls

from .api import api
from .views import media_access

urlpatterns = []

# REST API and OAuth2 provider — mounted outside i18n_patterns and before the
# startpage catch-all so they are not shadowed by a language prefix (a locale
# redirect would turn the frontend's token POST into a GET) or the "^" include.
urlpatterns += [
    path("api/", api.urls),
    path("o/", include(oauth2_urls)),
]

if settings.OIDC_ENABLED:
    urlpatterns += i18n_patterns(
        re_path(r"^oidc/", include("mozilla_django_oidc.urls")),
    )

# NOTE: ``/kompass`` is deliberately absent. It used to serve the Django admin;
# the Kompass SPA now owns that path and is served in front of Django, so this
# URLconf must not claim it.
urlpatterns += i18n_patterns(
    re_path(r"^media/(?P<path>.*)", media_access, name="media"),
    re_path(r"^newsletter/", include("mailer.urls", namespace="mailer")),
    re_path(r"^members/", include("members.urls", namespace="members")),
    re_path(r"^login/", include("logindata.urls", namespace="logindata")),
    re_path(
        r"^LBAlpin/Programm(/)?(20)?[0-9]{0,2}",
        include("ludwigsburgalpin.urls", namespace="ludwigsburgalpin"),
    ),
    re_path(r"^", include("startpage.urls", namespace="startpage")),
)

urlpatterns += [
    re_path(r"^markdownx/", include("markdownx.urls")),
]

handler404 = "startpage.views.handler404"
handler500 = "startpage.views.handler500"

# TODO: django serving from MEDIA_URL should be disabled in production stage
# see
# http://stackoverflow.com/questions/5871730/need-a-minimal-django-file-upload-example
