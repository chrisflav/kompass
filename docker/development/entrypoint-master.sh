#!/usr/bin/env bash

set -o errexit

sleep 5

cd /app

if ! [ -f completed_initial_run ]; then
    echo 'Initialising kompass master container'

    python jdav_web/manage.py compilemessages --locale de

    # python jdav_web/manage.py makemigrations
    python jdav_web/manage.py migrate

    touch completed_initial_run
fi

cd jdav_web

celery -A jdav_web worker -B --scheduler django_celery_beat.schedulers:DatabaseScheduler -l info &
python manage.py runserver 0.0.0.0:8000
