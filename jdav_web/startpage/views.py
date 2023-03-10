from django.shortcuts import redirect


# Create your views here.
def index(request):
    return redirect('https://www.alpenverein-ludwigsburg.de/gruppen/jugendgruppen')
