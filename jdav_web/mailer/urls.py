from django.urls import re_path

from . import views

app_name = "mailer"
urlpatterns = [
    re_path(r"^$", views.index, name="index"),
    re_path(r"^unsubscribe", views.unsubscribe, name="unsubscribe"),
]
