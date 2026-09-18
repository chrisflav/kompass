"""
LMTP endpoint that postfix delivers to instead of dovecot.

LMTP (RFC 2033) is the standard hand-off between an MTA and final delivery, so
this speaks the same protocol dovecot did and postfix needs only its
``virtual_transport`` repointed. It also lets us answer with real SMTP status
codes: a temporary problem becomes a ``4xx`` and postfix keeps the message and
retries, rather than the mail being silently dropped into a mailbox nobody
reads.

Recipients are accepted or rejected during RCPT, where a rejection is still
cheap and precise. Everything that can only be decided once the body is known
happens in DATA.
"""

import logging

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import close_old_connections

from . import bounce
from . import delivery
from . import munge as munging
from . import routing

logger = logging.getLogger(__name__)

BOUNCE = "bounce"


def _classify(address):
    """Decide what an incoming recipient address is, and whether we take it."""
    local_part, _ = routing.split_address(address)
    base, detail = routing.strip_detail(local_part)

    if base == settings.MAIL_BOUNCE_LOCAL_PART:
        if not detail:
            return None, "550 5.1.1 Malformed bounce address"
        return (BOUNCE, detail), None

    route = routing.resolve(local_part)
    if route is None:
        return None, "550 5.1.1 No such address"
    return route, None


def _with_connection(work):
    """Run ORM work with a connection that is known to be healthy.

    The LMTP server is long lived, so a connection idle since the last message
    may have been dropped by the database in the meantime. This belongs here
    at the thread boundary rather than inside the routing functions: closing a
    connection while a transaction is open would abort it.
    """
    close_old_connections()
    try:
        return work()
    finally:
        close_old_connections()


def _check_recipient(address, envelope_from):
    """Synchronous RCPT handling; returns the SMTP reply to send."""
    try:
        target, error = _classify(address)
    except Exception:
        logger.exception("Failed to resolve recipient %s.", address)
        return "451 4.3.0 Recipient resolution temporarily unavailable"

    if error is not None:
        return error
    if isinstance(target, tuple):
        return "250 2.1.5 Ok"

    allowed, reason = routing.sender_allowed(target, envelope_from)
    if not allowed:
        logger.info("Rejecting mail from %s to %s: %s", envelope_from, address, reason)
        return "550 5.7.1 {}".format(reason.capitalize())
    return "250 2.1.5 Ok"


def _deliver(address, envelope_from, content):
    """Synchronous DATA handling for a single recipient."""
    target, error = _classify(address)
    if error is not None:
        return error

    message = munging.parse(content)
    message_id = str(message.get("Message-ID", "")).strip()

    if isinstance(target, tuple):
        _, token = target
        bounce.handle(token, message)
        return "250 2.0.0 Bounce recorded"

    looping, why = munging.is_loop(
        message, target.address, max_received=settings.MAIL_MAX_RECEIVED_HEADERS
    )
    if looping:
        logger.warning("Dropping looping message to %s (%s).", target.address, why)
        return "554 5.4.6 Routing loop detected"

    if not message_id:
        # Without a Message-ID we cannot recognise a retry, so a deferral would
        # duplicate every copy. Synthesising one keeps delivery idempotent.
        message_id = "<generated-{}@{}>".format(
            delivery.DeliveryAttempt.new_token(), settings.DOMAIN
        )
        logger.info("Incoming message to %s had no Message-ID.", target.address)

    deferred = delivery.forward(message, target, envelope_from, message_id)
    if deferred:
        return "451 4.4.1 Could not forward to {}, will retry".format(", ".join(deferred))
    return "250 2.0.0 Forwarded"


class RouterHandler:
    """aiosmtpd handler translating LMTP delivery into kompass routing."""

    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        mail_from = envelope.mail_from or ""
        reply = await sync_to_async(_with_connection)(lambda: _check_recipient(address, mail_from))
        if reply.startswith("250"):
            envelope.rcpt_tos.append(address)
        return reply

    async def handle_DATA(self, server, session, envelope):
        content = envelope.original_content or envelope.content
        mail_from = envelope.mail_from or ""
        replies = []
        for address in envelope.rcpt_tos:
            try:
                replies.append(
                    await sync_to_async(_with_connection)(
                        lambda address=address: _deliver(address, mail_from, content)
                    )
                )
            except Exception:
                logger.exception("Unhandled error delivering to %s.", address)
                replies.append("451 4.3.0 Temporary delivery failure")
        # postfix is configured with one recipient per transaction, so the
        # worst reply is also the only reply in practice.
        for reply in replies:
            if not reply.startswith("250"):
                return reply
        return replies[0] if replies else "250 2.0.0 Ok"
