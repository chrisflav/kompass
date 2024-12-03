#!/usr/bin/env bash

set -o errexit

cd /app

if ! [ -f completed_initial_run ]; then
    echo 'Initialising kompass master container'

    cd docs
    make html
    cp -r build/html /app/jdav_web/static/docs
    cd /app

    python jdav_web/manage.py collectstatic --noinput
    python jdav_web/manage.py compilemessages --locale de

    python jdav_web/manage.py migrate

    touch completed_initial_run
fi

uwsgi --ini docker/production/kompass.uwsgi.ini
