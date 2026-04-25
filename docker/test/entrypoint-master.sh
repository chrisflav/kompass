#!/usr/bin/env bash

set -o errexit

HTMLCOV_DIR=/app/jdav_web/htmlcov

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

# Default verbosity to 2 if not set
VERBOSITY=${DJANGO_TEST_VERBOSITY:-2}

set +o errexit

if [[ "$DJANGO_TEST_KEEPDB" == 1 ]]; then
    coverage run manage.py test startpage finance members contrib logindata mailer material ludwigsburgalpin test_data jdav_web -v $VERBOSITY --noinput --keepdb 2>&1 | tee "$HTMLCOV_DIR/test_output.txt"
else
    coverage run manage.py test startpage finance members contrib logindata mailer material ludwigsburgalpin test_data jdav_web -v $VERBOSITY --noinput 2>&1 | tee "$HTMLCOV_DIR/test_output.txt"
fi
TEST_EXIT_CODE=${PIPESTATUS[0]}

set -o errexit

coverage html --show-contexts
coverage json -o htmlcov/coverage.json
coverage report --show-missing
coverage report --show-missing > htmlcov/coverage_report.txt

echo "$TEST_EXIT_CODE" > "$HTMLCOV_DIR/test_exit_code.txt"
echo "ok" > "$HTMLCOV_DIR/run_status.txt"

echo "Saved coverage report in htmlcov/coverage_report.txt. Exiting."

exit $TEST_EXIT_CODE
