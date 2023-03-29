#!/usr/bin/env bash

cd /app/jdav_web

celery -A jdav_web worker -l info
