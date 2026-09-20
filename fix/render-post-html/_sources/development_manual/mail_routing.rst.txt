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
(``hard_bounce_limit``), which stops kompass from sending to a
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

``munge_display_suffix`` is what recipients see: a message forwarded through
``info@`` arrives as ``Max Mustermann via Kompass <info@…>``, so set it to
something that names the association.

The router only accepts recipients in ``settings.DOMAIN``; anything else is
refused with ``550``, so the endpoint cannot be used as an open relay by
something else that can reach it. Keep the MTA's accepted domains in step with
that setting.


Mail server setup
=================

What has to be true
-------------------

The MTA has exactly two jobs. It must accept mail for the domain and hand it
to the router over LMTP, and it must hand the bounces back the same way. It
holds no forwarding rules, no alias tables and no recipient lists.

Bounces need no separate route. They are addressed to
``bounce+<token>@<domain>``, which is the same domain as everything else, so
whatever delivers ordinary mail to the router delivers those too. The router
splits the ``+<token>`` itself and does not depend on the MTA's
``recipient_delimiter``; it only matters that the delimiter in
``bounce_local_part`` addresses is the ``+`` the router expects.

Reaching the router
-------------------

The ``lmtp`` service listens on port 8024. How the MTA reaches it depends on
where it runs.

Running in the same compose project, the service name resolves directly and
nothing else is needed. Running as its own compose project — which the
`Kompass-tailored mailserver`_ does — the router has to join that project's
network, so declare it as external and attach the service to both:

.. code-block:: yaml

   services:
       lmtp:
           <<: *kompass
           entrypoint: /app/docker/production/entrypoint-lmtp.sh
           volumes:
             - ./config:/app/config:ro
           networks:
             - main
             - mailserver
           extra_hosts:
             - "host:10.26.42.1"

   networks:
     mailserver:
       external: true
       name: <mail server compose project>_main

Compose gives the service its own name as a network alias on both networks, so
the MTA addresses it as ``lmtp``. Do not publish port 8024 on the host: the
router forwards under a ``From:`` we sign, and anything that can reach the port
can have mail sent under it. Restricting recipients to ``settings.DOMAIN``
limits the damage but is not an authentication mechanism.

Postfix
-------

Point final delivery for the virtual domain at the router:

.. code-block:: console

   virtual_transport = lmtp:inet:lmtp:8024

That single setting replaces delivery to dovecot. Two more are worth having:

.. code-block:: console

   lmtp_destination_recipient_limit = 1
   recipient_delimiter = +

The first avoids a needless round trip, because the router takes one recipient
per transaction and defers the rest with ``452``. The second is conventional
rather than required, for the reason given above.

``reject_unverified_recipient`` keeps working and now probes the router, which
answers authoritatively for every address, so the probe is accurate but
redundant; it can be dropped from ``smtpd_recipient_restrictions`` along with
``address_verify_map``.

Nothing else in the MTA needs to know about kompass. In particular the sieve
rules that used to query the database, and the scripts they called, are dead
once ``virtual_transport`` points here and should be removed rather than left
to rot next to a live config.

Filtering still belongs in the MTA. The router forwards what it is given, and
a message relayed to twenty external mailboxes under a ``From:`` we sign is
exactly what a spam filter is for.

Verifying it
------------

Check that the router resolves addresses before sending anything through it.
From a shell that can reach port 8024:

.. code-block:: python

   import smtplib

   class LMTP(smtplib.SMTP):
       def lhlo(self, name=""):
           self.putcmd("lhlo", name or self.local_hostname)
           return self.getreply()

   s = LMTP("lmtp", 8024)
   s.lhlo("probe")
   s.mail("probe@example.org")
   print(s.rcpt("info@your-domain.example"))       # 250, a configured address
   print(s.rcpt("nobody@your-domain.example"))     # 550, unknown
   print(s.rcpt("info@somewhere-else.example"))    # 550, wrong domain

A ``RCPT`` probe resolves the address without delivering anything, so it is
safe against a list with real members behind it.

Then send one real message and follow it. In the MTA log the inbound delivery
should end at the router, and a second queue entry should leave with a bounce
address as its envelope sender:

.. code-block:: console

   to=<info@your-domain.example>, relay=lmtp[…]:8024, status=sent (250 2.0.0 Forwarded)
   from=<bounce+…@your-domain.example>, size=…, nrcpt=1 (queue active)

Seeing the first line without the second means the router accepted the message
and then dropped it, which it only does for a loop or a suppressed duplicate —
both are logged by the ``lmtp`` service.

What the replies mean
---------------------

The status code the router returns is the whole operational interface, so it
is worth knowing what each one is telling you.

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Reply
     - Meaning
   * - ``250 Forwarded``
     - Every copy was handed to the outgoing server.
   * - ``250 Bounce recorded``
     - A delivery report was matched to its target address.
   * - ``451``
     - Something temporary: the database is unreachable, or the outgoing
       server would not take a copy. The MTA keeps the message and retries;
       copies that already went out are not repeated.
   * - ``452``
     - A second recipient in one transaction. The MTA delivers it separately.
   * - ``550``
     - The address does not exist, is not in our domain, or the sender is not
       allowed to write to it. Permanent, and the sender is told.
   * - ``554``
     - A loop was detected and the message was dropped deliberately.

A message that keeps coming back with ``451`` is the one case worth watching:
the MTA will retry it until its queue lifetime expires, so check the ``lmtp``
service log for the underlying error rather than waiting for the bounce.


.. _Kompass-tailored mailserver: https://git.jdav-hd.merten.dev/digitales/kompass-mailserver
