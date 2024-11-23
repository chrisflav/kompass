from django.urls import re_path

from . import views

app_name = "startpage"
urlpatterns = [
    re_path(r'^$', views.index, name='index'),
    re_path(r'^impressum/?$', views.static_view('startpage/impressum.html'), name='impressum'),
    re_path(r'^aktuelles/?$', views.aktuelles, name='aktuelles'),
    re_path(r'^berichte/?$', views.berichte, name='berichte'),
    re_path(r'^gruppen/?$', views.static_view('startpage/gruppen.html'), name='gruppen'),
    re_path(r'^gruppen/faq/?$', views.static_view('startpage/gruppen/faq.html'), name='faq'),
    re_path(r'^gruppen/(?P<group_name>[\w\-:]+)/?$', views.gruppe_detail, name='gruppe_detail'),
    re_path(r'^(?P<section_name>[\w\-:]+)/(?P<post_name>[\w\-:]+)/?$', views.post, name='post'),
    re_path(r'^(?P<section_name>[\w\-:]+)/?$', views.section, name='section'),
]
