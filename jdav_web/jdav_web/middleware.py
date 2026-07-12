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
