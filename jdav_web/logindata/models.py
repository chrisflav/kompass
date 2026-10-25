from django.conf import settings
from django.contrib.auth.models import Group as BaseAuthGroup
from django.contrib.auth.models import User as BaseUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class AuthGroup(BaseAuthGroup):
    class Meta:
        proxy = True
        verbose_name = _("Permission group")
        verbose_name_plural = _("Permission groups")


class LoginDatum(BaseUser):
    class Meta:
        proxy = True
        verbose_name = _("Login Datum")
        verbose_name_plural = _("Login Data")


class RegistrationPassword(models.Model):
    """
    A password that can be used to register after inviting a member.
    """

    password = models.CharField(max_length=100, verbose_name=_("Password"))

    def __str__(self):
        return self.password

    class Meta:
        verbose_name = _("Active registration password")
        verbose_name_plural = _("Active registration passwords")


class PersonalAccessToken(models.Model):
    """A bearer token a user creates in the web interface, for a script or an assistant.

    It is an ordinary django-oauth-toolkit access token without an application,
    so the API's bearer auth takes it unchanged. This row adds what the user
    named it and whether it may only read, which ``contrib.api.auth`` enforces.
    Revoking deletes the access token, and this row with it.
    """

    access_token = models.OneToOneField(
        "oauth2_provider.AccessToken", on_delete=models.CASCADE, related_name="personal"
    )
    name = models.CharField(_("name"), max_length=100)
    read_only = models.BooleanField(_("read only"), default=True)
    created = models.DateTimeField(_("created"), auto_now_add=True)
    # The owner is the access token's user; a superuser may create a token for
    # another account, and this keeps who did.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("created by"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Personal access token")
        verbose_name_plural = _("Personal access tokens")
        ordering = ["-created", "-pk"]
        default_permissions = ()
        permissions = [("create_personalaccesstoken", _("Can create personal access tokens"))]


class TOTPDevice(models.Model):
    """An authenticator app, confirmed with a code before it was saved.

    The shared secret is stored encrypted (see ``logindata.two_factor``), so a
    copy of the database alone does not yield working codes. ``last_counter``
    is the time step of the last accepted code: a code is accepted only for a
    later step, so one seen over a shoulder cannot be used a second time.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="totp_devices"
    )
    name = models.CharField(_("name"), max_length=100)
    encrypted_secret = models.TextField()
    last_counter = models.BigIntegerField(default=0)
    created = models.DateTimeField(_("created"), auto_now_add=True)
    last_used = models.DateTimeField(_("last used"), null=True, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Authenticator app")
        verbose_name_plural = _("Authenticator apps")
        ordering = ["created", "pk"]
        default_permissions = ()


class WebAuthnCredential(models.Model):
    """A security key or passkey, registered through WebAuthn.

    ``discoverable`` records whether the authenticator reported keeping the
    credential itself (a resident key) and verified the user while creating
    it. Only such a credential signs in without a password.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="webauthn_credentials"
    )
    name = models.CharField(_("name"), max_length=100)
    # base64url, as the browser reports it.
    credential_id = models.CharField(max_length=1024, unique=True)
    public_key = models.BinaryField()
    sign_count = models.BigIntegerField(default=0)
    discoverable = models.BooleanField(default=False)
    created = models.DateTimeField(_("created"), auto_now_add=True)
    last_used = models.DateTimeField(_("last used"), null=True, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Security key")
        verbose_name_plural = _("Security keys")
        ordering = ["created", "pk"]
        default_permissions = ()


class RecoveryCode(models.Model):
    """A one-time code for when no second factor is at hand.

    Only a SHA-256 hash is stored. The codes carry 80 random bits, which makes
    a slow password hash unnecessary, and lets a code be found by its hash.
    A code is deleted when it is used.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recovery_codes"
    )
    code_hash = models.CharField(max_length=64)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(fields=["user", "code_hash"], name="unique_recovery_code")
        ]


class TwoFactorAttempts(models.Model):
    """Failed second-factor and re-authentication attempts of one account.

    Kept in the database rather than the cache: the cache ignores its own
    failures, and a lockout that silently stops counting is none.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="two_factor_attempts"
    )
    failures = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        default_permissions = ()


class TwoFactorSetup(models.Model):
    """A factor being added: the secret or challenge between its two requests.

    The API's ``state`` names one of these by ``nonce``. Saving the factor
    deletes it, so a state works once; starting another setup replaces it. The
    value is encrypted like a TOTP secret.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=20)
    nonce = models.CharField(max_length=64, unique=True)
    encrypted_value = models.TextField()
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()


def initial_user_setup(user, member):
    try:
        standard_group = AuthGroup.objects.get(name="Standard")
    except AuthGroup.DoesNotExist:
        return False

    user.is_staff = True
    user.save()
    user.groups.add(standard_group)
    member.user = user
    member.invite_as_user_key = ""
    member.save()
    return True
