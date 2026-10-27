"""
This file contains code for using the Kompass as an OAuth2 provider. For the reverse
direction see `jdav_web/logindata/oidc.py`.
"""

import logging

from oauth2_provider.oauth2_validators import OAuth2Validator

from . import two_factor

logger = logging.getLogger(__name__)


class CustomOAuth2Validator(OAuth2Validator):
    # Set `oidc_claim_scope = None` to ignore scopes that limit which claims to return,
    # otherwise the OIDC standard scopes are used.

    def validate_user(self, username, password, client, request, *args, **kwargs):
        """The password grant: refused for an account with a second factor.

        This grant swaps a username and password for a token with no second
        step at all, so for such an account it would be a way around it. Only a
        password that checks out *and* an account without a factor pass;
        anything else, an error included, refuses.
        """
        try:
            if not super().validate_user(username, password, client, request, *args, **kwargs):
                return False
            return not two_factor.required_for(request.user)
        except Exception:
            logger.exception("Refusing the password grant after an error.")
            return False

    def get_additional_claims(self, request):
        if request.user.member:
            context = {"email": request.user.member.email}
        else:
            context = {}
        return dict(context, preferred_username=request.user.username)
