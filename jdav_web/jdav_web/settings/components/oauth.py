# ruff: noqa F821

OAUTH2_PROVIDER = {
    "OIDC_ENABLED": True,
    # The SPA is a public client: PKCE is what keeps its authorization code
    # useless to anyone who intercepts it.
    "PKCE_REQUIRED": True,
    "OAUTH2_VALIDATOR_CLASS": "logindata.oauth.CustomOAuth2Validator",
    "OIDC_RSA_PRIVATE_KEY": get_var("oauth", "oidc_rsa_private_key", default=""),
    "SCOPES": {
        "openid": "OpenID Connect scope",
        "profile": "profile scope",
        "email": "email scope",
    },
}
