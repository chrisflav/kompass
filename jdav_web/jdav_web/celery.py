import os

from celery import Celery

# set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "jdav_web.settings")

app = Celery()
app.config_from_object("django.conf:settings")
app.autodiscover_tasks()

if __name__ == "__main__":
    app.start()  # pragma: no cover
