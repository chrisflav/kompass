class ForceLangMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.META["HTTP_ACCEPT_LANGUAGE"] = "de"
        return self.get_response(request)
