# ruff: noqa F821

# Database
# https://docs.djangoproject.com/en/1.10/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": get_var("database", "database", default="jdav_db"),
        "USER": get_var("database", "user", default="user"),
        "PASSWORD": get_var("database", "password", default="secret"),
        "HOST": get_var("database", "host", default="127.0.0.1"),
        "PORT": get_var("database", "port", default=5432),
    }
}
