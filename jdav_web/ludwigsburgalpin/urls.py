from django.conf.urls import url

from . import views

app_name = "ludwigsburgalpin"
urlpatterns = [
    url(r'^$', views.index, name='index')
    # url(r'^subscribe', views.subscribe, name='subscribe'),
]
