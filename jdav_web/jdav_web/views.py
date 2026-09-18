import re
from urllib.parse import quote

from django.conf import settings
from django.contrib import admin
from django.contrib.auth.views import LoginView
from django.contrib.auth.views import redirect_to_login
from django.http import Http404
from django.http import HttpResponse
from django.shortcuts import render
from django.views.static import serve
from startpage.models import Link


class BuiltinLoginView(LoginView):
    """Django's own login form, served only where no identity provider exists.

    The OAuth2 authorization endpoint sends an anonymous visitor to
    ``settings.LOGIN_URL``, and the admin's login is no use there: it lives
    under ``/kompass``, which the new frontend's router owns on its domain, and
    anything inside ``i18n_patterns`` is answered with a locale redirect into
    that router. So this form stands in — but only where sign-in is not already
    handled by a provider.

    Where OIDC is configured this must not exist at all: ``ModelBackend`` is
    always in ``AUTHENTICATION_BACKENDS``, so a reachable password form would be
    a way around the provider's MFA and deprovisioning for anyone still holding
    a local password. The check is here rather than in the urlconf so it is
    decided per request, which is both testable in either mode and impossible to
    leave behind by editing a route.
    """

    def dispatch(self, request, *args, **kwargs):
        if settings.OIDC_ENABLED:
            raise Http404("No local login form where an identity provider is configured.")
        return super().dispatch(request, *args, **kwargs)


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
