from django.core.management.base import BaseCommand
from mailer.models import Message
from members.models import Member
from django.db.models import Q

import re


class Command(BaseCommand):
    help = 'Shows reply-to addresses'
    requires_system_checks = False

    def add_arguments(self, parser):
        parser.add_argument('--message_id', default="-1")
        parser.add_argument('--subject', default="")

    def handle(self, *args, **options):
        replies = []
        try:
            message_id = int(options['message_id'])
            message = Message.objects.get(pk=message_id)
            if message.reply_to:
                replies = list(message.reply_to.all())
                replies.extend(message.reply_to_email_address.all())
        except (Message.DoesNotExist, ValueError):
            extracted = re.match("^([Ww][Gg]: *|[Ff][Ww]: *|[Rr][Ee]: *|[Aa][Ww]: *)* *(.*)$",
                                 options['subject']).group(2)
            try:
                msgs = Message.objects.filter(subject=extracted)
                message = msgs.all()[0]
                if message.reply_to:
                    replies = message.reply_to.all()
                    replies.extend(message.reply_to_email_address.all())
            except (Message.DoesNotExist, ValueError, IndexError):
                pass

        if not replies:
            # send mail to all jugendleiters
            replies = Member.objects.filter(group__name='Jugendleiter',
                                            gets_newsletter=True)
        forwards = [l.email for l in replies]

        self.stdout.write(" ".join(forwards))
