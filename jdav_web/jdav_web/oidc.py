from django.conf import settings
from mozilla_django_oidc.auth import OIDCAuthenticationBackend


class MyOIDCAB(OIDCAuthenticationBackend):
    def get_username(self, claims):
        """
        Extract the username from the given claims by looking for
        an entry with key OIDC_CLAIM_USERNAME.
        If the claims don't contain the username, a hash is produced.
        """
        username = claims.get(settings.OIDC_CLAIM_USERNAME)

        if username is None:
            return super().get_username(claims)

        return username

    def filter_users_by_claims(self, claims):
        """
        Return the users matching the username obtained from the claims.
        """
        username = self.get_username(claims)
        return self.UserModel.objects.filter(username=username)

    def create_user(self, claims):
        """
        Create a user from the given claims.
        """
        user = super().create_user(claims)
        return self.update_user(user, claims)

    def update_user(self, user, claims):
        """
        Update an existing user with the given claims.
        This sets the staff (resp. superuser) access if the claims contain the respective groups.
        """
        groups = claims.get("groups", [])

        if settings.OIDC_GROUP_STAFF in groups:
            user.is_staff = True
        if settings.OIDC_GROUP_SUPERUSER in groups:
            user.is_superuser = True

        user.save()
        return user
