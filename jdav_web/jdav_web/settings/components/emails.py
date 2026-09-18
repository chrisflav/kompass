# ruff: noqa F821

# Email setup

EMAIL_HOST = get_var("mail", "host", default="localhost")
EMAIL_PORT = get_var("mail", "port", default=587 if deployed else 25)
EMAIL_HOST_USER = get_var("mail", "user", default="user")
EMAIL_HOST_PASSWORD = get_var("mail", "password", default="secret")
EMAIL_USE_TLS = get_var("mail", "tls", default=True if deployed else False)

# Use console backend if configured, otherwise use Celery backend
EMAIL_USE_CONSOLE_BACKEND = get_var("mail", "use_console_backend", default=False)
if EMAIL_USE_CONSOLE_BACKEND:  # pragma: no cover
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
else:
    EMAIL_BACKEND = "djcelery_email.backends.CeleryEmailBackend"

# Celery Email Setup

CELERY_EMAIL_TASK_CONFIG = {
    "rate_limit": "10/m"  # * CELERY_EMAIL_CHUNK_SIZE (default: 10)
}

DEFAULT_SENDING_MAIL = get_var("mail", "default_sending_address", default="kompass@localhost")
DEFAULT_SENDING_NAME = get_var("mail", "default_sending_name", default="Kompass")

# Incoming mail routing
#
# Postfix delivers incoming mail here over LMTP instead of to dovecot, and
# kompass resolves the recipients itself. See mailer/lmtp.py.

LMTP_HOST = get_var("mail", "lmtp_host", default="0.0.0.0")
LMTP_PORT = get_var("mail", "lmtp_port", default=8024)

# Envelope senders of forwarded copies are <local_part>+<token>@DOMAIN, which
# postfix splits on its recipient_delimiter and routes back to us.
MAIL_BOUNCE_LOCAL_PART = get_var("mail", "bounce_local_part", default="bounce")

# Appended to the author's name in the rewritten From, as mailing lists do.
MAIL_MUNGE_DISPLAY_SUFFIX = get_var("mail", "munge_display_suffix", default="via Kompass")

# How long a delivered copy suppresses a repeat of the same Message-ID. Long
# enough to cover an MTA's retries, short enough that a sender reusing an id
# is not silenced forever.
MAIL_DUPLICATE_WINDOW_DAYS = get_var("mail", "duplicate_window_days", default=7)

# Permanent bounces tolerated before an address stops being delivered to.
MAIL_HARD_BOUNCE_LIMIT = get_var("mail", "hard_bounce_limit", default=3)

# Guard against forwarding loops and oversized messages.
MAIL_MAX_RECEIVED_HEADERS = get_var("mail", "max_received_headers", default=25)
MAIL_MAX_MESSAGE_SIZE = get_var("mail", "max_message_size", default=52428800)
