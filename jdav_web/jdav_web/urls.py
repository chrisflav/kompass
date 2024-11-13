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
from django.urls import re_path, include
from django.contrib import admin
from django.conf.urls.static import static
from django.conf.urls.i18n import i18n_patterns
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.views.generic.base import RedirectView

urlpatterns = static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.index_title = _('Startpage')
admin.site.site_header = 'Kompass'

urlpatterns += i18n_patterns(
    re_path(r'^kompass/?', admin.site.urls),
    re_path(r'^jet/', include('jet.urls', 'jet')), # Django JET URLS
    re_path(r'^admin/?', RedirectView.as_view(url='/kompass')),
    re_path(r'^newsletter/', include('mailer.urls', namespace="mailer")),
    re_path(r'^members/', include('members.urls', namespace="members")),
    re_path(r'^LBAlpin/Programm(/)?(20)?[0-9]{0,2}', include('ludwigsburgalpin.urls',
            namespace="ludwigsburgalpin")),
    re_path(r'^_nested_admin/', include('nested_admin.urls')),
    re_path(r'^', include('startpage.urls', namespace="startpage")),
)

urlpatterns += [
    re_path(r'^markdownx/', include('markdownx.urls')),
]

handler404 = 'startpage.views.handler404'
handler500 = 'startpage.views.handler500'

# TODO: django serving from MEDIA_URL should be disabled in production stage
# see
# http://stackoverflow.com/questions/5871730/need-a-minimal-django-file-upload-example
