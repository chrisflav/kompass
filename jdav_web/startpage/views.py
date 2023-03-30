from django.shortcuts import redirect
from django.conf import settings


# Create your views here.
def index(request):
    return redirect(settings.STARTPAGE_REDIRECT_URL)
