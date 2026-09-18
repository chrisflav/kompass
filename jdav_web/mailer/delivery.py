"""
Forwarding of an incoming message to the targets of its route.

Postfix keeps the message in its queue until we accept it, so this module does
not need a queue of its own: a target that cannot be delivered right now is
reported back to postfix, which retries the whole message later. Because a
retry replays targets that already succeeded, every copy is recorded first and
skipped on subsequent attempts.
"""

import logging
from smtplib import SMTPException

from django.conf import settings
from django.core.mail import get_connection
from django.utils import timezone

from . import munge as munging
from .models import DeliveryAttempt
from .models import MailDeliveryState

logger = logging.getLogger(__name__)


def send_raw(envelope_from, recipient, message_bytes):
    """Hand one rendered message to the outgoing SMTP server."""
    connection = get_connection(backend="django.core.mail.backends.smtp.EmailBackend")
    connection.open()
    try:
        connection.connection.sendmail(envelope_from, [recipient], message_bytes)
    finally:
        connection.close()


def _attempt_for(message_id, recipient, route, envelope_from, subject):
    """Fetch or create the record for one copy.

    ``get_or_create`` retries the lookup inside a savepoint if a concurrent
    delivery inserted the row first, which is exactly the unique constraint we
    have, so a redelivery racing with itself resolves to the same record.
    """
    return DeliveryAttempt.objects.get_or_create(
        message_id=message_id,
        recipient=recipient,
        defaults={
            "token": DeliveryAttempt.new_token(),
            "address": route.address,
            "envelope_from": envelope_from[:254],
            "subject": subject[:255],
        },
    )[0]


def forward(message, route, envelope_from, message_id):
    """Deliver ``message`` to every target of ``route``.

    Returns the list of targets that could not be delivered. An empty list
    means the message may be accepted; anything else has to be deferred so
    postfix retries.
    """
    munged = munging.munge(
        message,
        list_address=route.address,
        display_suffix=settings.MAIL_MUNGE_DISPLAY_SUFFIX,
    )
    payload = munging.serialize(munged)
    subject = str(munged.get("Subject", ""))

    suspended = MailDeliveryState.suspended_addresses(route.targets)
    deferred = []

    for recipient in route.targets:
        if recipient in suspended:
            logger.info("Skipping suspended address %s for %s.", recipient, route.address)
            continue

        attempt = _attempt_for(message_id, recipient, route, envelope_from, subject)
        if attempt.sent_at is not None:
            logger.debug("Copy to %s already delivered, skipping on retry.", recipient)
            continue

        try:
            send_raw(attempt.bounce_address(), recipient, payload)
        except (SMTPException, OSError) as error:
            logger.warning("Could not forward %s to %s: %s", route.address, recipient, error)
            deferred.append(recipient)
            continue

        attempt.sent_at = timezone.now()
        attempt.save(update_fields=["sent_at"])

    return deferred
