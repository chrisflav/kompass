# ruff: noqa F821

# Authentication

AUTHENTICATION_BACKENDS = (
    "jdav_web.oidc.MyOIDCAB",
    "django.contrib.auth.backends.ModelBackend",
    "rules.permissions.ObjectPermissionBackend",
)

# Use Open ID Connect if possible
OIDC_ENABLED = get_var("oidc", "enabled", default=False)

# OIDC configuration
OIDC_RP_CLIENT_ID = get_var("oidc", "rp_client_id", default="")
OIDC_RP_CLIENT_SECRET = get_var("oidc", "rp_client_secret", default="")
OIDC_OP_AUTHORIZATION_ENDPOINT = get_var("oidc", "op_authorization_endpoint", default="")
OIDC_OP_TOKEN_ENDPOINT = get_var("oidc", "op_token_endpoint", default="")
OIDC_OP_USER_ENDPOINT = get_var("oidc", "op_user_endpoint", default="")
OIDC_OP_JWKS_ENDPOINT = get_var("oidc", "op_jwks_endpoint", default="")

OIDC_RP_SIGN_ALGO = get_var("oidc", "rp_sign_algo", default="RS256")
OIDC_RP_SCOPES = get_var("oidc", "rp_scopes", default="openid email profile")

OIDC_CLAIM_USERNAME = get_var("oidc", "claim_username", default="username")
OIDC_CLAIM_FIRST_NAME = get_var("oidc", "claim_first_name", default="given_name")
OIDC_CLAIM_LAST_NAME = get_var("oidc", "claim_last_name", default="last_name")
OIDC_GROUP_STAFF = get_var("oidc", "group_staff", default="staff")
OIDC_GROUP_SUPERUSER = get_var("oidc", "group_superuser", default="superuser")

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
