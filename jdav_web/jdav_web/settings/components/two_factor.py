# ruff: noqa F821

# Two-factor authentication for the built-in login (see logindata.two_factor).
# Where OIDC is enabled, the identity provider owns the second factor instead.

# WebAuthn binds a security key to a relying party ID, a domain, and accepts an
# assertion only from the origins listed here. Every origin must be that domain
# or a subdomain of it. The default domain is the one Django is served on; the
# default origins are every page the login form is served on: Django's own
# host, the frontend, and the second frontend domain proxying `/accounts/`.
WEBAUTHN_RP_ID = get_var("two_factor", "webauthn_rp_id", default=HOST.split(":")[0])
WEBAUTHN_RP_NAME = get_var("two_factor", "webauthn_rp_name", default="Kompass")
WEBAUTHN_ORIGINS = list(
    get_var(
        "two_factor",
        "webauthn_origins",
        default=[
            origin.rstrip("/")
            for origin in ["{}://{}".format(PROTOCOL, HOST), FRONTEND_BASE_URL]
            + CSRF_TRUSTED_ORIGINS
            if origin
        ],
    )
)

# How long the second step of a login waits after the password, in seconds.
TWO_FACTOR_PENDING_SECONDS = 300
# Every this many attempts without a successful second factor (codes at login,
# wrong passwords when changing factors) lock an account's second step: first
# for TWO_FACTOR_LOCKOUT_SECONDS, then twice as long each time, up to
# TWO_FACTOR_MAX_LOCKOUT_SECONDS.
TWO_FACTOR_MAX_FAILURES = 5
TWO_FACTOR_LOCKOUT_SECONDS = 900
TWO_FACTOR_MAX_LOCKOUT_SECONDS = 24 * 3600
