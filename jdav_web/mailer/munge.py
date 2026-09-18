"""
Rewriting of forwarded messages so that they survive DMARC.

A forwarded message keeps the author's ``From:`` domain but is transmitted by
us, so the author's SPF does not cover us and their DKIM signature rarely
survives the relay. Receivers then apply the author's DMARC policy and reject.
The established fix, used by every mailing list manager, is to take authorship:
the ``From:`` becomes our own address, which our SPF and DKIM do cover, and the
original author moves to ``Reply-To:``.
"""

import logging
from email import message_from_bytes
from email import policy
from email.utils import formataddr
from email.utils import parseaddr

logger = logging.getLogger(__name__)

#: Headers that are invalidated by rewriting ``From:`` or that must not be
#: inherited from the incoming message. Signatures covering the old ``From:``
#: would fail verification, and a stale ``Authentication-Results`` from our own
#: hostname would be indistinguishable from one the receiver added itself.
STRIPPED_HEADERS = (
    "from",
    "return-path",
    "sender",
    "dkim-signature",
    "domainkey-signature",
    "arc-seal",
    "arc-message-signature",
    "arc-authentication-results",
    "authentication-results",
    "received-spf",
)


def parse(raw):
    """Parse raw message bytes into a mutable message object."""
    return message_from_bytes(raw, policy=policy.default)


def munge(message, list_address, display_suffix, loop_token=None):
    """Rewrite ``message`` in place so we become its author.

    ``list_address`` is the address the mail came in on, which becomes the new
    ``From:``. The original author is preserved in ``Reply-To`` unless the
    message already carries one, in which case the author's own reply path
    wins. ``loop_token`` is recorded in ``X-Loop`` so that a message coming
    back around can be recognised.
    """
    original_from = message.get("From", "")
    display_name, author = parseaddr(original_from)
    existing_reply_to = message.get("Reply-To")

    for header in STRIPPED_HEADERS:
        del message[header]
    del message["Reply-To"]

    message["From"] = formataddr(
        ("{} {}".format(display_name or author, display_suffix).strip(), list_address)
    )
    if existing_reply_to:
        message["Reply-To"] = existing_reply_to
    elif author:
        message["Reply-To"] = formataddr((display_name, author))
    if author:
        message["X-Original-From"] = original_from
    message["X-Loop"] = loop_token or list_address
    return message


def is_loop(message, loop_token, max_received=25):
    """Detect a message that is circling back to us.

    Two independent signals: our own ``X-Loop`` marker coming back, and an
    implausible number of ``Received`` headers, which catches loops through
    forwarders that drop unknown headers.
    """
    for value in message.get_all("X-Loop", []):
        if value.strip().lower() == loop_token.lower():
            return True, "X-Loop"
    if len(message.get_all("Received", [])) > max_received:
        return True, "too many Received headers"
    return False, ""


def serialize(message):
    """Render the message for transmission over SMTP."""
    return message.as_bytes(policy=policy.SMTP)
