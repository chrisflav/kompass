from django.urls import re_path

from . import views

app_name = "mailer"
urlpatterns = [
    re_path(r'^echo', views.echo , name='echo'),
]
