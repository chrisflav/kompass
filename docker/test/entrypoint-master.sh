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

if ! [ -f /tmp/completed_initial_run ]; then
    echo 'Initialising kompass master container'

    python jdav_web/manage.py compilemessages --locale de
fi

cd jdav_web

if [[ "$DJANGO_TEST_KEEPDB" == 1 ]]; then
    coverage run manage.py test startpage finance members contrib logindata mailer material ludwigsburgalpin jdav_web -v 2 --noinput --keepdb
else
    coverage run manage.py test startpage finance members contrib logindata mailer material ludwigsburgalpin jdav_web -v 2 --noinput
fi
coverage html
coverage json
coverage report
