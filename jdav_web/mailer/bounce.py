"""
Processing of delivery status notifications for forwarded mail.

Every forwarded copy leaves with a unique envelope sender, so the bounce that
may come back hours later identifies exactly one target address rather than
landing in a shared mailbox nobody reads.
"""

import logging

from django.utils import timezone

from .models import DeliveryAttempt
from .models import MailDeliveryState

logger = logging.getLogger(__name__)


def parse_status(message):
    """Extract ``(permanent, status, detail)`` from a DSN (RFC 3464).

    Falls back to treating an unparseable report as a soft failure: suspending
    an address on a report we did not understand is worse than retrying.
    """
    action = ""
    status = ""
    for part in message.walk():
        if part.get_content_type() != "message/delivery-status":
            continue
        for field_block in part.get_payload():
            action = action or str(field_block.get("Action", ""))
            status = status or str(field_block.get("Status", ""))
    permanent = action.strip().lower() == "failed" and status.strip().startswith("5")
    detail = "action={} status={}".format(action.strip(), status.strip())
    return permanent, status.strip(), detail


def handle(token, message):
    """Record a bounce for the copy identified by ``token``.

    Returns ``True`` if the token was known. An unknown token is not an error:
    backscatter to a made up bounce address is common, and a report can arrive
    for an attempt from before this system was in place.
    """
    attempt = DeliveryAttempt.objects.filter(token=token).first()
    if attempt is None:
        logger.info("Bounce for unknown token %s, ignoring.", token)
        return False

    if attempt.bounced_at is not None:
        # The same report can arrive twice if a transaction is redelivered;
        # counting it again would suspend an address early.
        logger.info("Bounce for %s already recorded, ignoring repeat.", attempt.recipient)
        return True

    permanent, status, detail = parse_status(message)
    attempt.bounced_at = timezone.now()
    attempt.bounce_status = status[:32]
    attempt.save(update_fields=["bounced_at", "bounce_status"])

    state, _ = MailDeliveryState.objects.get_or_create(email=attempt.recipient)
    state.record_bounce(permanent=permanent, status=status, detail=detail)
    logger.info(
        "Recorded %s bounce for %s (%s).",
        "permanent" if permanent else "transient",
        attempt.recipient,
        status or "no status",
    )
    return True
