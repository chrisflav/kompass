.. _development_manual/mail_routing:

============
Mail routing
============

Kompass resolves incoming mail itself. The MTA receives a message, hands it to
the ``lmtp`` service over LMTP, and kompass decides who it goes to, rewrites it
and sends the copies back out. The MTA keeps no forwarding rules of its own.

Why kompass routes
==================

The forwarding targets live in kompass: :class:`~mailer.models.EmailAddress`
resolves to individual members and to whole groups, and a member's personal
address resolves to whatever external address they configured. Answering the
question inside kompass means there is no rule set to export, synchronise or
invalidate, and no second system holding a stale copy of the membership.

Personal addresses and configured addresses use the same code path. A personal
address is simply a :class:`~mailer.routing.Route` with a single target.

Why the message is rewritten
============================

A forwarded message keeps its author's ``From:`` domain but is transmitted by
us. The author's SPF record does not cover our server, and their DKIM signature
rarely survives the relay, so the receiver applies the author's DMARC policy and
rejects the mail. This is not a misconfiguration that can be tuned away; it is
what forwarding does.

Every forwarded message therefore takes our own address as ``From:``, with the
author moved to ``Reply-To:`` and named in the display name, exactly as a
mailing list does. ``From:`` then aligns with the SPF and DKIM records we do
control. See :mod:`mailer.munge`.

Why LMTP
========

LMTP (:rfc:`2033`) is the standard hand-off between an MTA and final delivery,
so any MTA can talk to the router and swapping MTAs is a configuration change.

It also carries real status codes, which decides what happens when something
breaks. A database that cannot be reached answers ``451`` and the MTA keeps the
message and retries. An unknown address answers ``550`` and the sender is told.
Neither case can silently swallow a message.

LMTP expects one reply per accepted recipient after ``DATA`` and the server
library sends exactly one, so the router accepts a single recipient per
transaction and answers ``452`` to any further one. The MTA then delivers those
separately. Setting ``lmtp_destination_recipient_limit = 1`` avoids the extra
round trip, but nothing breaks without it.

Bounces
=======

Each copy leaves with its own envelope sender,
``bounce+<token>@<domain>``, recorded as a
:class:`~mailer.models.DeliveryAttempt`. A bounce arriving hours later carries
that token back, so it identifies exactly one target address rather than
landing in a shared mailbox.

Repeated permanent bounces suspend the address
(:setting:`MAIL_HARD_BOUNCE_LIMIT`), which stops kompass from sending to a
mailbox that no longer exists. Suspended addresses are listed in the admin under
*Mail delivery states* and can be reactivated there.

Retries and duplicates
======================

The MTA queue is the only queue. When a copy cannot be delivered the router
answers ``451`` and the MTA redelivers the whole message later, including the
targets that already succeeded. Those are recognised by their
:class:`~mailer.models.DeliveryAttempt` and skipped, so a deferral never
duplicates mail. A message that arrives without a ``Message-ID`` is keyed by a
hash of its content instead, so that it too replays safely.

That key is the sender's, and nothing stops one from reusing it, so the record
only suppresses a repeat for ``duplicate_window_days``. Beyond that the message
is delivered again rather than silently dropped forever.

A relay that refuses a recipient outright with a ``5xx`` is not a deferral: the
address is recorded as having hard bounced, exactly as if the report had come
back later, and the remaining targets still go out.

Configuration
=============

.. code-block:: toml

   [mail]
   lmtp_host = "0.0.0.0"
   lmtp_port = 8024
   bounce_local_part = "bounce"
   munge_display_suffix = "via Kompass"
   hard_bounce_limit = 3
   duplicate_window_days = 7

The MTA needs two things: it must deliver mail for the domain to the router,
and it must route ``bounce+*`` back to it. With postfix that is
``virtual_transport = lmtp:inet:<host>:8024`` and ``recipient_delimiter = +``.

The router only accepts recipients in ``settings.DOMAIN``; anything else is
refused with ``550``, so the endpoint cannot be used as an open relay by
something else that can reach it. Keep the MTA's accepted domains in step with
that setting.
