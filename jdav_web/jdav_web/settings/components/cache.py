CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.memcached.PyMemcacheCache',
        'LOCATION': os.environ.get('MEMCACHED_URL', '127.0.0.1:11211'),
    }
}

CACHE_MIDDLEWARE_ALIAS = 'default'
CACHE_MIDDLEWARE_SECONDS = 120
CACHE_MIDDLEWARE_KEY_PREFIX = ''

