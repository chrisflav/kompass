import re
from urllib.parse import quote

from django.conf import settings
from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.shortcuts import render
from django.views.static import serve
from startpage.models import Link


def media_unprotected(request, path):
    if settings.DEBUG:
        # if DEBUG is enabled, directly serve file
        return serve(request, path, document_root=settings.MEDIA_ROOT)
    # otherwise create a redirect to the internal nginx endpoint at /protected
    response = HttpResponse()
    # Content-type will be detected by nginx
    del response["Content-Type"]
    response["X-Accel-Redirect"] = "/protected/" + quote(path, safe="/")
    return response


@staff_member_required
def media_protected(request, path):
    return media_unprotected(request, path)


def media_access(request, path):
    if re.match("^(people|images)/", path):
        return media_unprotected(request, path)
    else:
        return media_protected(request, path)


_APP_DOCUMENTATION_URLS = {
    "members": "user_manual/members.html",
    "finance": "user_manual/finance.html",
}


def custom_admin_view(request):
    """
    this methods provides access to models in order to render a custom admin page index site.
    """
    app_list = admin.site.get_app_list(request)
    context = {
        "app_list": app_list,
        "site_header": admin.site.site_header,
        "site_title": admin.site.site_title,
        "external_links": Link.objects.all(),
        "documentation_url": "user_manual/getstarted.html",
    }
    return render(request, "admin/index.html", context)


_original_app_index = admin.site.__class__.app_index


def custom_app_index(request, app_label):
    extra_context = {}
    if app_label in _APP_DOCUMENTATION_URLS:
        extra_context["documentation_url"] = _APP_DOCUMENTATION_URLS[app_label]
    return _original_app_index(admin.site, request, app_label, extra_context)


admin.site.index = custom_admin_view
admin.site.app_index = custom_app_index
