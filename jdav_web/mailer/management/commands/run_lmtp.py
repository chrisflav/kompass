"""Run the LMTP endpoint that postfix delivers incoming mail to."""

import asyncio
import logging
import signal

from aiosmtpd.controller import Controller
from aiosmtpd.lmtp import LMTP
from django.conf import settings
from django.core.management.base import BaseCommand
from mailer.lmtp import RouterHandler

logger = logging.getLogger(__name__)


class LMTPController(Controller):
    """Controller serving LMTP rather than SMTP."""

    def factory(self):
        # Controller passes its extra kwargs to the SMTP class it builds, but
        # only through its own factory, so they have to be repeated here.
        return LMTP(
            self.handler,
            hostname=settings.DOMAIN,
            enable_SMTPUTF8=True,
            data_size_limit=settings.MAIL_MAX_MESSAGE_SIZE,
        )


class Command(BaseCommand):
    help = "Serve LMTP so postfix can deliver incoming mail to kompass."

    def add_arguments(self, parser):
        parser.add_argument("--host", default=settings.LMTP_HOST)
        parser.add_argument("--port", type=int, default=settings.LMTP_PORT)

    def handle(self, *args, **options):
        controller = LMTPController(
            RouterHandler(),
            hostname=options["host"],
            port=options["port"],
        )
        controller.start()
        self.stdout.write(
            self.style.SUCCESS(
                "LMTP router listening on {}:{}".format(options["host"], options["port"])
            )
        )

        stop = asyncio.Event()
        loop = asyncio.new_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        try:
            loop.run_until_complete(stop.wait())
        finally:
            controller.stop()
            loop.close()
            self.stdout.write("LMTP router stopped.")
