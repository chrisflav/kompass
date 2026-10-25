"""Personal access tokens: created, listed and revoked by their owner.

A token is shown once, in the answer that creates it; afterwards only its name,
rights and dates are listed. Creating one takes
``logindata.create_personalaccesstoken``; listing and revoking one's own tokens
does not, so someone who loses the permission can still end the tokens they
made. All three need the web interface's own sign-in — a token issued to the
frontend — so no other token, personal or issued to a third-party application,
can mint a longer-lived or wider one, list the tokens, or revoke them.

Superusers also create tokens for other accounts — a bot account that never
signs in, say — and see and revoke every account's tokens.
"""

import secrets
from datetime import datetime
from datetime import timedelta
from datetime import timezone as dt_timezone

from contrib.api.perms import authorize
from contrib.api.perms import Forbidden
from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from logindata.models import PersonalAccessToken
from ninja import Router
from ninja import Schema
from oauth2_provider.models import get_access_token_model

router = Router()

# The lifetimes offered when creating a token, besides never expiring.
LIFETIME_DAYS = (7, 30, 90)
# The toolkit requires an expiry; a token that never expires gets the latest
# moment the database stores, and is listed without one.
NEVER = datetime(9999, 12, 31, tzinfo=dt_timezone.utc)
# Recognisable in a leaked config file or a secret scanner's rules.
TOKEN_PREFIX = "kompass_pat_"


class PersonalTokenIn(Schema):
    """A new token: what to call it, whether it may write, how many days it lives.

    ``days`` null makes a token that never expires. ``user_id`` names another
    account to create it for, which only a superuser may.
    """

    name: str
    read_only: bool = True
    days: int | None = 30
    user_id: int | None = None


class TokenOwner(Schema):
    id: int
    username: str


class PersonalTokenOut(Schema):
    id: int
    name: str
    read_only: bool
    created: datetime
    # Null for a token that never expires.
    expires: datetime | None
    user: TokenOwner
    # Who created it, which differs from ``user`` for a superuser's token for
    # another account; null once that account is deleted.
    created_by: TokenOwner | None


class PersonalTokenCreated(PersonalTokenOut):
    """The created token, the one time its secret is shown."""

    token: str


def require_session(request):
    """Refuse any bearer token but one the frontend obtained by signing in."""
    access_token = getattr(request, "access_token", None)
    application = access_token.application if access_token is not None else None
    if application is None or application.client_id != settings.FRONTEND_OAUTH_CLIENT_ID:
        raise Forbidden(_("Access tokens can only be managed after signing in."))


def _owner(user):
    return {"id": user.pk, "username": user.username} if user is not None else None


def _out(personal):
    access_token = personal.access_token
    return {
        "id": personal.pk,
        "name": personal.name,
        "read_only": personal.read_only,
        "created": personal.created,
        "expires": None if access_token.expires >= NEVER else access_token.expires,
        "user": _owner(access_token.user),
        "created_by": _owner(personal.created_by),
    }


def _visible_tokens(request):
    """Every account's tokens for a superuser, one's own for anyone else."""
    tokens = PersonalAccessToken.objects.select_related("access_token__user", "created_by")
    if request.user.is_superuser:
        return tokens
    return tokens.filter(access_token__user=request.user)


@router.get("/tokens", response=list[PersonalTokenOut])
def list_tokens(request):
    """The personal access tokens the requesting user manages, newest first."""
    require_session(request)
    return [_out(t) for t in _visible_tokens(request)]


@router.post("/tokens", response={201: PersonalTokenCreated})
def create_token(request, payload: PersonalTokenIn):
    """Create a token for the requesting user; the answer is the only time it is shown."""
    authorize(request, "logindata.create_personalaccesstoken")
    require_session(request)
    name = payload.name.strip()
    if not name:
        raise ValidationError({"name": [_("Give the token a name.")]})
    if payload.days is not None and payload.days not in LIFETIME_DAYS:
        raise ValidationError({"days": [_("Choose one of the offered lifetimes.")]})
    owner = request.user
    if payload.user_id is not None and payload.user_id != request.user.pk:
        if not request.user.is_superuser:
            raise Forbidden(_("Only superusers can create tokens for other accounts."))
        owner = get_object_or_404(User, pk=payload.user_id)
    if payload.days is None:
        expires = NEVER
    else:
        expires = timezone.now() + timedelta(days=payload.days)
    with transaction.atomic():
        access_token = get_access_token_model().objects.create(
            user=owner,
            token=TOKEN_PREFIX + secrets.token_urlsafe(32),
            expires=expires,
            scope="read" if payload.read_only else "read write",
        )
        personal = PersonalAccessToken.objects.create(
            access_token=access_token,
            name=name,
            read_only=payload.read_only,
            created_by=request.user,
        )
    return 201, {**_out(personal), "token": access_token.token}


@router.delete("/tokens/{token_id}", response={204: None})
def revoke_token(request, token_id: int):
    """Revoke a token the requesting user manages; it stops working at once."""
    require_session(request)
    personal = get_object_or_404(_visible_tokens(request), pk=token_id)
    # Deleting the access token takes the personal row with it (CASCADE).
    personal.access_token.delete()
    return 204, None
