# ruff: noqa F821

# The frontend is a public client, so PKCE is what keeps its authorization code
# useless to anyone who intercepts it. Scoped to that one client id rather than
# set globally: this provider also serves confidential third-party applications
# registered through /o/applications/, and requiring PKCE of them would refuse
# every authorization request they already make. django-oauth-toolkit calls this
# with the client id and expects a bool (see OAuth2Validator.is_pkce_required).
FRONTEND_OAUTH_CLIENT_ID = get_var("oauth", "frontend_client_id", default="kompass-frontend-dev")


def _pkce_required(client_id):
    return client_id == FRONTEND_OAUTH_CLIENT_ID


# The toolkit's models are swappable; the migration autodetector reads this
# setting as soon as a model refers to the access token (logindata's personal
# access tokens do), and the toolkit only defaults it inside its own settings.
OAUTH2_PROVIDER_ACCESS_TOKEN_MODEL = "oauth2_provider.AccessToken"

OAUTH2_PROVIDER = {
    "OIDC_ENABLED": True,
    "PKCE_REQUIRED": _pkce_required,
    "OAUTH2_VALIDATOR_CLASS": "logindata.oauth.CustomOAuth2Validator",
    "OIDC_RSA_PRIVATE_KEY": get_var("oauth", "oidc_rsa_private_key", default=""),
    "SCOPES": {
        "openid": "OpenID Connect scope",
        "profile": "profile scope",
        "email": "email scope",
    },
}
