from django.urls import re_path

from . import views

app_name = "mailer"
urlpatterns = [
    re_path(r'^echo', views.echo , name='echo'),
    re_path(r'^registration', views.invited_registration , name='registration'),
    re_path(r'^register', views.register , name='register'),
    re_path(r'^waitinglist', views.register_waiting_list , name='register_waiting_list'),
    re_path(r'^mail/confirm', views.confirm_mail , name='confirm_mail'),
]
