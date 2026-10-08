# ruff: noqa F821

# `cache_backend` for the same reason as the database engine: a test run with no memcached
# names Django's local-memory cache instead.
#
# One dict rather than a branch per backend. The options below are pymemcache's, and a backend
# that does not know them ignores them -- `BaseCache.__init__` reads only the keys it defines
# out of `OPTIONS` and hands the rest to a client that, for LocMemCache, does not exist. A
# branch would read as the safer choice and is not: it would be a line no deployment executes,
# and this project's test gate requires every line to be.
CACHES = {
    "default": {
        "BACKEND": get_var(
            "django", "cache_backend", default="django.core.cache.backends.memcached.PyMemcacheCache"
        ),
        "LOCATION": get_var("django", "memcached_url", default="cache:11211"),
        "OPTIONS": {
            "no_delay": True,
            "ignore_exc": True,
            "max_pool_size": 4,
            "use_pooling": True,
        },
    }
}

CACHE_MIDDLEWARE_ALIAS = "default"
CACHE_MIDDLEWARE_SECONDS = 1
CACHE_MIDDLEWARE_KEY_PREFIX = ""
