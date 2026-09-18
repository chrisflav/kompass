"""
Forwarding of an incoming message to the targets of its route.

Postfix keeps the message in its queue until we accept it, so this module does
not need a queue of its own: a target that cannot be delivered right now is
reported back to postfix, which retries the whole message later. Because a
retry replays targets that already succeeded, every copy is recorded first and
skipped on subsequent attempts.
"""

import logging
from smtplib import SMTPDataError
from smtplib import SMTPException
from smtplib import SMTPRecipientsRefused
from smtplib import SMTPSenderRefused

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


def _already_delivered(attempt):
    """Whether this copy went out recently enough to treat a repeat as a retry.

    The key is the sender's Message-ID, which nothing stops a sender from
    reusing. Without a bound, a device that reuses one would have every later
    message silently accepted and dropped, so the record only suppresses
    redeliveries for as long as an MTA would plausibly still be retrying.
    """
    if attempt.sent_at is None:
        return False
    age = timezone.now() - attempt.sent_at
    return age.days < settings.MAIL_DUPLICATE_WINDOW_DAYS


def _record_refusal(attempt, error):
    """Note a synchronous 5xx from the relay against the target address."""
    attempt.bounced_at = timezone.now()
    attempt.bounce_status = "5.0.0"
    attempt.save(update_fields=["bounced_at", "bounce_status"])
    state, _created = MailDeliveryState.objects.get_or_create(email=attempt.recipient)
    state.record_bounce(permanent=True, status="5.0.0", detail=str(error)[:2000])


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
        if _already_delivered(attempt):
            logger.debug("Copy to %s already delivered, skipping on retry.", recipient)
            continue

        try:
            send_raw(attempt.bounce_address(), recipient, payload)
        except (SMTPRecipientsRefused, SMTPSenderRefused, SMTPDataError) as error:
            # The relay refused this address outright. Retrying cannot help, and
            # it is the clearest failure signal we get, so record it like the
            # bounce it is instead of making the MTA redeliver for days.
            logger.warning("Relay refused %s for %s: %s", recipient, route.address, error)
            _record_refusal(attempt, error)
            continue
        except (SMTPException, OSError) as error:
            logger.warning("Could not forward %s to %s: %s", route.address, recipient, error)
            deferred.append(recipient)
            continue

        attempt.sent_at = timezone.now()
        attempt.save(update_fields=["sent_at"])

    return deferred
