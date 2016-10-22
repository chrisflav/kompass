from django.conf.urls import url

from . import views

app_name = "mailer"
urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(r'^send_mail', views.send_mail, name='send_mail'),
    url(r'^send', views.send, name='send')
]
