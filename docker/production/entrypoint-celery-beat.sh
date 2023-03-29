#!/usr/bin/env bash

cd /app/jdav_web

celery -A jdav_web beat --scheduler django_celery_beat.schedulers:DatabaseScheduler -l info
