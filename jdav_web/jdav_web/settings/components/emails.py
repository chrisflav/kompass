# ruff: noqa F821

# Email setup

EMAIL_HOST = get_var("mail", "host", default="localhost")
EMAIL_PORT = get_var("mail", "port", default=587 if deployed else 25)
EMAIL_HOST_USER = get_var("mail", "user", default="user")
EMAIL_HOST_PASSWORD = get_var("mail", "password", default="secret")
EMAIL_USE_TLS = get_var("mail", "tls", default=True if deployed else False)

# Use console backend if configured, otherwise use Celery backend
EMAIL_USE_CONSOLE_BACKEND = get_var("mail", "use_console_backend", default=False)
if EMAIL_USE_CONSOLE_BACKEND:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
else:
    EMAIL_BACKEND = "djcelery_email.backends.CeleryEmailBackend"

# Celery Email Setup

CELERY_EMAIL_TASK_CONFIG = {
    "rate_limit": "10/m"  # * CELERY_EMAIL_CHUNK_SIZE (default: 10)
}

DEFAULT_SENDING_MAIL = get_var("mail", "default_sending_address", default="kompass@localhost")
DEFAULT_SENDING_NAME = get_var("mail", "default_sending_name", default="Kompass")
