#!/usr/bin/env bash

set -o errexit

mysql_ready() {
cd /app/jdav_web
python << END
import sys

from django.db import connections
from django.db.utils import OperationalError

db_conn = connections['default']

try:
    c = db_conn.cursor()
except OperationalError:
    sys.exit(-1)
else:
    sys.exit(0)

END
}

until mysql_ready; do
    >&2 echo 'Waiting for MySQL to become available...'
    sleep 1
done
>&2 echo 'MySQL is available'

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
