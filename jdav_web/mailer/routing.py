"""
Resolution of incoming mail addresses to their forwarding targets.

Both kinds of forwarding collapse onto the same :class:`Route` type: a
personal address is simply a route with a single target. Everything
downstream of :func:`resolve` therefore treats them identically.
"""

import logging
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Q

logger = logging.getLogger(__name__)

PERSONAL = "personal"
LIST = "list"


@dataclass(frozen=True)
class Route:
    """Where mail to a local address has to go."""

    #: local part the mail was addressed to
    local_part: str
    #: ``personal`` for a member's own address, ``list`` for a configured one
    kind: str
    #: external addresses to forward to, never empty
    targets: tuple[str, ...]
    #: the configured address, if this is a list route
    email_address: object = None

    @property
    def address(self):
        return "{}@{}".format(self.local_part, settings.DOMAIN)


def split_address(address, casefold=True):
    """Split ``local@domain`` into its local part and domain.

    Lowercased by default, since addresses are matched case insensitively.
    Callers that carry a case sensitive payload in the local part — the bounce
    token does — pass ``casefold=False`` and fold only what they compare.
    The domain is optional so that callers may pass a bare local part.
    """
    address = (address or "").strip()
    if casefold:
        address = address.lower()
    if "@" not in address:
        return address, ""
    local, _, domain = address.partition("@")
    return local, domain


def strip_detail(local_part):
    """Remove an ``+detail`` suffix, matching postfix' recipient_delimiter."""
    base, _, detail = local_part.partition("+")
    return base, detail


def resolve(address):
    """Return the :class:`Route` for ``address``, or ``None`` if unknown.

    A configured :class:`~mailer.models.EmailAddress` takes precedence over a
    member's personal address, mirroring the order the sieve rules used.
    """
    from .models import EmailAddress

    local_part, _ = split_address(address)
    if not local_part:
        return None

    email_address = EmailAddress.objects.filter(name__iexact=local_part).first()
    if email_address is not None:
        targets = tuple(sorted(target for target in email_address.forwards if target))
        if not targets:
            logger.warning("Address %s has no forwarding targets configured.", local_part)
            return None
        return Route(
            local_part=email_address.name,
            kind=LIST,
            targets=targets,
            email_address=email_address,
        )

    user = User.objects.filter(username__iexact=local_part).select_related("member").first()
    member = getattr(user, "member", None) if user is not None else None
    if member is not None and member.email:
        return Route(local_part=local_part, kind=PERSONAL, targets=(member.email,))

    return None


def sender_allowed(route, envelope_from):
    """Check the sender restrictions configured on a list route.

    Personal routes are unrestricted. Returns ``(allowed, reason)`` where
    ``reason`` is a human readable explanation for the rejection.
    """
    from members.models import Member

    email_address = route.email_address
    if email_address is None:
        return True, ""

    _, domain = split_address(envelope_from)

    if email_address.internal_only:
        allowed_domains = settings.ALLOWED_EMAIL_DOMAINS_FOR_INVITE_AS_USER
        if "*" not in allowed_domains and domain not in allowed_domains:
            return False, "address accepts internal senders only"

    allowed_groups = email_address.allowed_senders.all()
    if allowed_groups:
        # Both addresses count: a member writing from the alternative address
        # they registered is still that member, and rejecting them here is
        # permanent rather than a deferral.
        senders = Member.objects.filter(
            Q(email__iexact=envelope_from) | Q(alternative_email__iexact=envelope_from),
            group__in=allowed_groups,
        )
        if not senders.exists():
            return False, "sender is not a member of an allowed group"

    return True, ""
