# ruff: noqa F821
# REST API (django-ninja) and CORS configuration.
# Loaded after components/base.py so it can extend INSTALLED_APPS / MIDDLEWARE.

INSTALLED_APPS += ["corsheaders"]

# CorsMiddleware must run before CommonMiddleware; place it just after
# SecurityMiddleware.
MIDDLEWARE.insert(
    MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1,
    "corsheaders.middleware.CorsMiddleware",
)

# Stop the site-wide cache middleware from storing /api/ responses (which are
# per-user, bearer-authenticated and must never be shared across users).
# Placed just inside UpdateCacheMiddleware so it runs before that middleware's
# process_response decides whether to cache.
MIDDLEWARE.insert(
    MIDDLEWARE.index("django.middleware.cache.UpdateCacheMiddleware") + 1,
    "jdav_web.middleware.ApiNoCacheMiddleware",
)

CORS_ALLOWED_ORIGINS = list(get_var("api", "cors_allowed_origins", default=[]))
CORS_ALLOW_CREDENTIALS = get_var("api", "cors_allow_credentials", default=False)

# Rate limits applied to the whole ninja API (see jdav_web/api.py). These are a
# coarse DoS backstop, keyed by client IP for unauthenticated requests (the
# public secret-key/read surfaces) and by user for authenticated ones. Rates use
# django-ninja's "<num>/<period>" syntax (period: s, m, h, d). Defaults are
# deliberately generous; tighten them in production settings.toml (and prefer an
# edge/reverse-proxy rate limit as the first line of defence).
API_ANON_THROTTLE_RATE = get_var("api", "anon_throttle_rate", default="1000/m")
API_AUTH_THROTTLE_RATE = get_var("api", "auth_throttle_rate", default="2000/m")

# Allow the local Vite dev server (frontend prototype) during development.
if DEBUG:
    CORS_ALLOWED_ORIGINS += [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
