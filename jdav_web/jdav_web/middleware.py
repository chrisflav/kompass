from django.conf import settings
from django.core.exceptions import DisallowedHost


class ForceLangMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.META["HTTP_ACCEPT_LANGUAGE"] = "de"
        return self.get_response(request)


class ApiNoCacheMiddleware:
    """Prevent the site-wide cache middleware from caching ``/api/`` responses.

    The API is bearer-authenticated and per-user; a cached response served to a
    different user would leak data. Setting ``_cache_update_cache`` to ``False``
    tells ``UpdateCacheMiddleware`` not to store the response, and the explicit
    ``Cache-Control`` header keeps intermediaries from caching it either.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/api/"):
            request._cache_update_cache = False
            response["Cache-Control"] = "private, no-store"
        return response


class ForwardedProtoForHostsMiddleware:
    """Honour ``X-Forwarded-Proto`` for named hosts only.

    ``SECURE_PROXY_SSL_HEADER`` is process-wide, and one process serves every
    domain this deployment answers for. Turning it on to satisfy a newly added
    domain would also flip ``request.is_secure()`` for the domain that has
    always run without it, and Django gates strict CSRF ``Referer`` checking on
    exactly that (``CsrfViewMiddleware.process_view``) — so a POST that used to
    be accepted could start being refused.

    Scoping it to the hosts in ``TRUST_FORWARDED_PROTO_HOSTS`` keeps the older
    domain byte-for-byte as it was, while the new one gets the scheme its proxy
    reports. Only hosts whose traffic cannot reach the container except through
    that proxy belong in the list: anything able to connect directly could
    otherwise choose the scheme Django believes.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.hosts = set(settings.TRUST_FORWARDED_PROTO_HOSTS)

    def __call__(self, request):
        if self.hosts and request.META.get("HTTP_X_FORWARDED_PROTO") == "https":
            # `get_host()` raises for a host outside ALLOWED_HOSTS; that request
            # is rejected anyway, so leave the scheme alone and let it be.
            try:
                host = request.get_host()
            except DisallowedHost:
                host = None
            if host in self.hosts:
                request.META["wsgi.url_scheme"] = "https"
        return self.get_response(request)
