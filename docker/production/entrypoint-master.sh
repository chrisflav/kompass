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
    python jdav_web/manage.py ensuresuperuser

    # Populate test data on staging environments only
    if [ "$POPULATE_TEST_DATA" = "true" ]; then
        echo 'Populating test data for staging environment...'
        python jdav_web/manage.py populate_test_data
    fi

    touch completed_initial_run
fi

uwsgi --ini docker/production/kompass.uwsgi.ini
