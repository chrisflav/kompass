from django.conf import settings
from mozilla_django_oidc.auth import OIDCAuthenticationBackend


class MyOIDCAB(OIDCAuthenticationBackend):
    def filter_users_by_claims(self, claims):
        username = claims.get(settings.OIDC_CLAIM_USERNAME)
        if not username:
            return self.UserModel.objects.none()

        return self.UserModel.objects.filter(username=username)

    def get_username(self, claims):
        username = claims.get(settings.OIDC_CLAIM_USERNAME, "")

        if not username:
            return super().get_username(claims)

        return username

    def get_userinfo(self, access_token, id_token, payload):
        return super().get_userinfo(access_token, id_token, payload)

    def create_user(self, claims):
        user = super().create_user(claims)
        return self.update_user(user, claims)

    def update_user(self, user, claims):
        user.first_name = claims.get(settings.OIDC_CLAIM_FIRST_NAME, "")
        user.last_name = claims.get(settings.OIDC_CLAIM_LAST_NAME, "")
        groups = claims.get("groups", [])

        if settings.OIDC_GROUP_STAFF in groups:
            user.is_staff = True
        if settings.OIDC_GROUP_SUPERUSER in groups:
            user.is_superuser = True

        user.save()

        return user
