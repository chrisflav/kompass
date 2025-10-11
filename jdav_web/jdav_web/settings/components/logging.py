import os

DJANGO_LOG_LEVEL = get_var('logging', 'django_level', default='INFO')
ROOT_LOG_LEVEL = get_var('logging', 'level', default='INFO')
LOG_ERROR_TO_EMAIL = get_var('logging', 'email_admins', default=False)
LOG_EMAIL_BACKEND = EMAIL_BACKEND if LOG_ERROR_TO_EMAIL else "django.core.mail.backends.console.EmailBackend"
LOG_ERROR_INCLUDE_HTML = get_var('logging', 'error_report_include_html', default=False)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
        "require_debug_true": {
            "()": "django.utils.log.RequireDebugTrue",
        },
    },
    "formatters": {
        "simple": {
            "format": "[{asctime}: {levelname}/{name}] {message}",
            "style": "{",
        },
        "verbose": {
            "format": "[{asctime}: {levelname}/{name}] {pathname}:{lineno} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "console_verbose": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "level": "ERROR",
        },
        "mail_admins": {
            "level": "ERROR",
            "class": "django.utils.log.AdminEmailHandler",
            "email_backend": LOG_EMAIL_BACKEND,
            "include_html": LOG_ERROR_INCLUDE_HTML,
            "filters": ["require_debug_false"],
        },
    },
    "root": {
        "handlers": ["console"],
        "level": ROOT_LOG_LEVEL,
    },
    "loggers": {
        "django": {
            "handlers": ["console", "mail_admins"],
            "level": DJANGO_LOG_LEVEL,
            "propagate": False,
        },
    },
}
