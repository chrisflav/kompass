"""Personal access tokens: created, listed and revoked by their owner.

A token is shown once, in the answer that creates it; afterwards only its name,
rights and dates are listed. Creating one takes
``logindata.create_personalaccesstoken``; listing and revoking one's own tokens
does not, so someone who loses the permission can still end the tokens they
made. Neither works with a personal access token itself: a token must not mint
longer-lived or wider tokens, nor revoke its owner's others.

Superusers also create tokens for other accounts — a bot account that never
signs in, say — and see and revoke every account's tokens.
"""

import secrets
from datetime import datetime
from datetime import timedelta
from datetime import timezone as dt_timezone

from contrib.api.perms import authorize
from contrib.api.perms import Forbidden
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


class PersonalTokenCreated(PersonalTokenOut):
    """The created token, the one time its secret is shown."""

    token: str


def _refuse_token_auth(request):
    if getattr(request, "personal_token", None) is not None:
        raise Forbidden(_("Access tokens can only be managed after signing in."))


def _out(personal):
    access_token = personal.access_token
    return {
        "id": personal.pk,
        "name": personal.name,
        "read_only": personal.read_only,
        "created": personal.created,
        "expires": None if access_token.expires >= NEVER else access_token.expires,
        "user": {"id": access_token.user.pk, "username": access_token.user.username},
    }


def _visible_tokens(request):
    """Every account's tokens for a superuser, one's own for anyone else."""
    tokens = PersonalAccessToken.objects.select_related("access_token__user")
    if request.user.is_superuser:
        return tokens
    return tokens.filter(access_token__user=request.user)


@router.get("/tokens", response=list[PersonalTokenOut])
def list_tokens(request):
    """The personal access tokens the requesting user manages, newest first."""
    return [_out(t) for t in _visible_tokens(request)]


@router.post("/tokens", response={201: PersonalTokenCreated})
def create_token(request, payload: PersonalTokenIn):
    """Create a token for the requesting user; the answer is the only time it is shown."""
    authorize(request, "logindata.create_personalaccesstoken")
    _refuse_token_auth(request)
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
            access_token=access_token, name=name, read_only=payload.read_only
        )
    return 201, {**_out(personal), "token": access_token.token}


@router.delete("/tokens/{token_id}", response={204: None})
def revoke_token(request, token_id: int):
    """Revoke a token the requesting user manages; it stops working at once."""
    _refuse_token_auth(request)
    personal = get_object_or_404(_visible_tokens(request), pk=token_id)
    # Deleting the access token takes the personal row with it (CASCADE).
    personal.access_token.delete()
    return 204, None
