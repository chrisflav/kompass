"""
This file contains code for using the Kompass as an OAuth2 provider. For the reverse
direction see `jdav_web/logindata/oidc.py`.
"""

from oauth2_provider.oauth2_validators import OAuth2Validator


class CustomOAuth2Validator(OAuth2Validator):
    # Set `oidc_claim_scope = None` to ignore scopes that limit which claims to return,
    # otherwise the OIDC standard scopes are used.

    def get_additional_claims(self, request):
        if request.user.member:
            context = {"email": request.user.member.email}
        else:
            context = {}
        return dict(context, preferred_username=request.user.username)
