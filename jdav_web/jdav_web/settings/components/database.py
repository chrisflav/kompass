# ruff: noqa F821

# Database
# https://docs.djangoproject.com/en/1.10/ref/settings/#databases

# `engine` so a run that has no database server can say so: the test path sets
# `django.db.backends.sqlite3` and a file under /tmp, which needs neither a server nor the
# `mysqlclient` extra. Defaults to MySQL, which is what every deployment uses.
DATABASES = {
    "default": {
        "ENGINE": get_var("database", "engine", default="django.db.backends.mysql"),
        "NAME": get_var("database", "database", default="kompass"),
        "USER": get_var("database", "user", default="kompass"),
        "PASSWORD": get_var("database", "password", default="secret"),
        "HOST": get_var("database", "host", default="db"),
        "PORT": get_var("database", "port", default=3306),
    }
}
