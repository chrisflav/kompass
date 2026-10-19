"""Personal access tokens: created, listed and revoked by their owner.

A token is shown once, in the answer that creates it; afterwards only its name,
rights and dates are listed. Creating one takes
``logindata.create_personalaccesstoken``; listing and revoking one's own tokens
does not, so someone who loses the permission can still end the tokens they
made. Neither works with a personal access token itself: a token must not mint
longer-lived or wider tokens, nor revoke its owner's others.
"""

import secrets
from datetime import datetime
from datetime import timedelta

from contrib.api.perms import authorize
from contrib.api.perms import Forbidden
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

# The lifetimes offered when creating a token; there is no token that never expires.
LIFETIME_DAYS = (7, 30, 90)
# Recognisable in a leaked config file or a secret scanner's rules.
TOKEN_PREFIX = "kompass_pat_"


class PersonalTokenIn(Schema):
    """A new token: what to call it, whether it may write, how many days it lives."""

    name: str
    read_only: bool = True
    days: int = 30


class PersonalTokenOut(Schema):
    id: int
    name: str
    read_only: bool
    created: datetime
    expires: datetime


class PersonalTokenCreated(PersonalTokenOut):
    """The created token, the one time its secret is shown."""

    token: str


def _refuse_token_auth(request):
    if getattr(request, "personal_token", None) is not None:
        raise Forbidden(_("Access tokens can only be managed after signing in."))


def _out(personal):
    return {
        "id": personal.pk,
        "name": personal.name,
        "read_only": personal.read_only,
        "created": personal.created,
        "expires": personal.access_token.expires,
    }


@router.get("/tokens", response=list[PersonalTokenOut])
def list_tokens(request):
    """The requesting user's own personal access tokens, newest first."""
    tokens = PersonalAccessToken.objects.filter(access_token__user=request.user)
    return [_out(t) for t in tokens.select_related("access_token")]


@router.post("/tokens", response={201: PersonalTokenCreated})
def create_token(request, payload: PersonalTokenIn):
    """Create a token for the requesting user; the answer is the only time it is shown."""
    authorize(request, "logindata.create_personalaccesstoken")
    _refuse_token_auth(request)
    name = payload.name.strip()
    if not name:
        raise ValidationError({"name": [_("Give the token a name.")]})
    if payload.days not in LIFETIME_DAYS:
        raise ValidationError({"days": [_("Choose one of the offered lifetimes.")]})
    with transaction.atomic():
        access_token = get_access_token_model().objects.create(
            user=request.user,
            token=TOKEN_PREFIX + secrets.token_urlsafe(32),
            expires=timezone.now() + timedelta(days=payload.days),
            scope="read" if payload.read_only else "read write",
        )
        personal = PersonalAccessToken.objects.create(
            access_token=access_token, name=name, read_only=payload.read_only
        )
    return 201, {**_out(personal), "token": access_token.token}


@router.delete("/tokens/{token_id}", response={204: None})
def revoke_token(request, token_id: int):
    """Revoke one of the requesting user's tokens; it stops working at once."""
    _refuse_token_auth(request)
    personal = get_object_or_404(PersonalAccessToken, pk=token_id, access_token__user=request.user)
    # Deleting the access token takes the personal row with it (CASCADE).
    personal.access_token.delete()
    return 204, None
