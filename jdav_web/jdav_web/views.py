import re
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponse
from django.views.static import serve


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


def media_protected(request, path):
    # Was ``@staff_member_required``, which defaults to redirecting at
    # ``admin:login`` — that no longer reverses now the admin is unmounted, so
    # the same staff check is spelled out against ``LOGIN_URL``.
    user = request.user
    if not (user.is_authenticated and user.is_active and user.is_staff):
        return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
    return media_unprotected(request, path)


def media_access(request, path):
    if re.match("^(people|images)/", path):
        return media_unprotected(request, path)
    else:
        return media_protected(request, path)
