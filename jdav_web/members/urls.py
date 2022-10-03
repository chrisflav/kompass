from django.urls import re_path

from . import views

app_name = "mailer"
urlpatterns = [
    re_path(r'^echo', views.echo , name='echo'),
    re_path(r'^register', views.register , name='register'),
    re_path(r'^mail/confirm', views.confirm_mail , name='confirm_mail'),
]
