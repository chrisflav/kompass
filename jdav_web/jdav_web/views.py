from django.http import HttpResponse
from django.views.static import serve
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required

@staff_member_required
def media_access(request, path):
    if settings.DEBUG:
        # if DEBUG is enabled, directly serve file
        return serve(request, path, document_root=settings.MEDIA_ROOT)
    # otherwise create a redirect to the internal nginx endpoint at /protected
    response = HttpResponse()
    # Content-type will be detected by nginx
    del response['Content-Type']
    response['X-Accel-Redirect'] = '/protected/' + path
    return response
