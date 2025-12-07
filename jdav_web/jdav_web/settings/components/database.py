# ruff: noqa F821

# Database
# https://docs.djangoproject.com/en/1.10/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": get_var("database", "database", default="kompass"),
        "USER": get_var("database", "user", default="kompass"),
        "PASSWORD": get_var("database", "password", default="secret"),
        "HOST": get_var("database", "host", default="db"),
        "PORT": get_var("database", "port", default=3306),
    }
}
