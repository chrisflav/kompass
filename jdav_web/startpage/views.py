from django.shortcuts import redirect


# Create your views here.
def index(request):
    return redirect('http://www.alpenverein-ludwigsburg.de/index.php?id=122')
