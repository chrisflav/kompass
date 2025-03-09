OAUTH2_PROVIDER = {
    "OIDC_ENABLED": True,
    "PKCE_REQUIRED": False,
    "OAUTH2_VALIDATOR_CLASS": "logindata.oauth.CustomOAuth2Validator",
    "OIDC_RSA_PRIVATE_KEY": get_var('oauth', 'oidc_rsa_private_key', default=''),
    "SCOPES": {
        "openid": "OpenID Connect scope",
        "profile": "profile scope",
        "email": "email scope",
    },
}
