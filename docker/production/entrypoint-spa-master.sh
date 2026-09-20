#!/usr/bin/env bash

set -o errexit

cd /app

# Deliberately no migrate / collectstatic / ensuresuperuser: the master
# container owns those, and running them from two processes at once is how a
# half-applied migration happens. This one only serves.

uwsgi --ini docker/production/kompass-spa.uwsgi.ini
