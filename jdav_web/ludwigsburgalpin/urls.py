from django.urls import re_path

from . import views

app_name = "ludwigsburgalpin"
urlpatterns = [
    re_path(r"^$", views.index, name="index")
    # re_path(r'^subscribe', views.subscribe, name='subscribe'),
]
