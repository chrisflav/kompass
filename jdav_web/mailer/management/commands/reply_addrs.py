from django.core.management.base import BaseCommand
from mailer.models import Message
from members.models import Member
import subprocess


class Command(BaseCommand):
    help = 'Shows reply-to addresses'
    requires_system_checks = False

    def add_arguments(self, parser):
        parser.add_argument('message_id', nargs='?', default="-1")

    def handle(self, *args, **options):
        replies = []
        try:
            message_id = int(options['message_id'])
            message = Message.objects.get(pk=message_id)
            if message.reply_to:
                replies = message.reply_to.all()
        except (Message.DoesNotExist, ValueError):
            pass

        if not replies:
            # send mail to all jugendleiters
            replies = Member.objects.filter(group__name='Jugendleiter',
                                            gets_newsletter=True)
        forwards = [l.email for l in replies]

        self.stdout.write(" ".join(forwards))
