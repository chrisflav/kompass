from django.http import HttpResponse
from django.views.static import serve
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required

import re


def media_unprotected(request, path):
    if settings.DEBUG:
        # if DEBUG is enabled, directly serve file
        return serve(request, path, document_root=settings.MEDIA_ROOT)
    # otherwise create a redirect to the internal nginx endpoint at /protected
    response = HttpResponse()
    # Content-type will be detected by nginx
    del response['Content-Type']
    response['X-Accel-Redirect'] = '/protected/' + path
    return response


@staff_member_required
def media_protected(request, path):
    return media_unprotected(request, path)


def media_access(request, path):
    if re.match('^(people|images)/', path):
        return media_unprotected(request, path)
    else:
        return media_protected(request, path)
