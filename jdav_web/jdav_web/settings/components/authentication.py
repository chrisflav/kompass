# ruff: noqa F821

# Authentication

AUTHENTICATION_BACKENDS = (
    "jdav_web.oidc.MyOIDCAB",
    "django.contrib.auth.backends.ModelBackend",
    "rules.permissions.ObjectPermissionBackend",
)

# Use Open ID Connect if possible
OIDC_ENABLED = "1" == os.environ.get("OIDC_ENABLED", "0")

# OIDC configuration
OIDC_RP_CLIENT_ID = os.environ.get("OIDC_RP_CLIENT_ID", "")
OIDC_RP_CLIENT_SECRET = os.environ.get("OIDC_RP_CLIENT_SECRET", "")
OIDC_OP_AUTHORIZATION_ENDPOINT = os.environ.get("OIDC_OP_AUTHORIZATION_ENDPOINT", "")
OIDC_OP_TOKEN_ENDPOINT = os.environ.get("OIDC_OP_TOKEN_ENDPOINT", "")
OIDC_OP_USER_ENDPOINT = os.environ.get("OIDC_OP_USER_ENDPOINT", "")
OIDC_OP_JWKS_ENDPOINT = os.environ.get("OIDC_OP_JWKS_ENDPOINT", "")

OIDC_RP_SIGN_ALGO = os.environ.get("OIDC_RP_SIGN_ALGO", "RS256")
OIDC_RP_SCOPES = os.environ.get("ODIC_RP_SCOPES", "openid email profile")

OIDC_CLAIM_USERNAME = os.environ.get("OIDC_CLAIM_USERNAME", "username")
OIDC_CLAIM_FIRST_NAME = os.environ.get("OIDC_CLAIM_FIRST_NAME", "given_name")
OIDC_CLAIM_LAST_NAME = os.environ.get("OIDC_CLAIM_LAST_NAME", "last_name")
OIDC_GROUP_STAFF = os.environ.get("OIDC_GROUP_STAFF", "staff")
OIDC_GROUP_SUPERUSER = os.environ.get("OIDC_GROUP_STAFF", "superuser")

LOGIN_REDIRECT_URL = "/kompass"
LOGOUT_REDIRECT_URL = "/"

# default login URL, is not used if OIDC is not enabled
LOGIN_URL = "/oidc/authenticate/"

# Password validation
# https://docs.djangoproject.com/en/1.10/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]
