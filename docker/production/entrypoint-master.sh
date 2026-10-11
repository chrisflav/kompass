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

# Unconditional, and after `migrate`: the section's finance rules live in its
# configuration directory, and a pull that changed them has to be picked up on
# the next start rather than on the next release. An unchanged package hashes
# to the version already stored, so this is a no-op most of the time. A package
# that fails its checks is stored as a draft, the previous version stays
# active, and the command says so loudly -- which must not stop the container
# from serving, hence the `|| true`.
python jdav_web/manage.py importruleset || true

uwsgi --ini docker/production/kompass.uwsgi.ini
