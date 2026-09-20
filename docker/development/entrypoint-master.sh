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

# Unconditional: the source tree is bind-mounted, so a `.po` updated on the
# host (by a pull, a rebase or `make dev messages`) leaves the compiled `.mo`
# behind, and gettext silently falls back to the msgid — the English source
# string — for every message added since the catalogue was last built.
# A subshell so the rest of the script keeps its own working directory;
# scoped to the project tree, which is where every catalogue lives.
(cd jdav_web && python manage.py compilemessages --locale de -v 0)

if ! [ -f /tmp/completed_initial_run ]; then
    echo 'Initialising kompass master container'

    cd docs
    make html
    cd /app

    # python jdav_web/manage.py makemigrations
    python jdav_web/manage.py migrate

    touch /tmp/completed_initial_run
fi

cd jdav_web

celery -A jdav_web worker -B --scheduler django_celery_beat.schedulers:DatabaseScheduler -l info &
python manage.py runserver 0.0.0.0:8000
