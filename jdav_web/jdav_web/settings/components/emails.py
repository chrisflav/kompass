# Email setup

EMAIL_HOST = os.environ.get('EMAIL_HOST', 'localhost')
EMAIL_PORT = 587 if deployed else 25
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = True if deployed else False
EMAIL_BACKEND = 'djcelery_email.backends.CeleryEmailBackend'

# Celery Email Setup

CELERY_EMAIL_TASK_CONFIG = {
    'rate_limit' : '10/m'  # * CELERY_EMAIL_CHUNK_SIZE (default: 10)
}

DEFAULT_SENDING_MAIL = os.environ.get('EMAIL_SENDING_ADDRESS', 'django@localhost')
