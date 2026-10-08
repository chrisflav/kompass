# ruff: noqa F821

# `cache_backend` for the same reason as the database engine: a test run with no memcached
# names Django's local-memory cache instead. The options below are pymemcache's and mean
# nothing to any other backend, so they travel with it.
_cache_backend = get_var(
    "django", "cache_backend", default="django.core.cache.backends.memcached.PyMemcacheCache"
)

if _cache_backend.endswith("PyMemcacheCache"):
    CACHES = {
        "default": {
            "BACKEND": _cache_backend,
            "LOCATION": get_var("django", "memcached_url", default="cache:11211"),
            "OPTIONS": {
                "no_delay": True,
                "ignore_exc": True,
                "max_pool_size": 4,
                "use_pooling": True,
            },
        }
    }
else:
    CACHES = {"default": {"BACKEND": _cache_backend}}

CACHE_MIDDLEWARE_ALIAS = "default"
CACHE_MIDDLEWARE_SECONDS = 1
CACHE_MIDDLEWARE_KEY_PREFIX = ""
