from django.urls import re_path

from . import views

app_name = "mailer"
urlpatterns = [
    re_path(r'^echo', views.echo , name='echo'),
    re_path(r'^registration', views.invited_registration , name='registration'),
    re_path(r'^register/download', views.download_registration_form, name='download_registration_form'),
    re_path(r'^register/upload', views.upload_registration_form , name='upload_registration_form'),
    re_path(r'^register', views.register , name='register'),
    re_path(r'^waitinglist/confirm', views.confirm_waiting , name='confirm_waiting'),
    re_path(r'^waitinglist/invitation/reject', views.reject_invitation , name='reject_invitation'),
    re_path(r'^waitinglist', views.register_waiting_list , name='register_waiting_list'),
    re_path(r'^mail/confirm', views.confirm_mail , name='confirm_mail'),
]
