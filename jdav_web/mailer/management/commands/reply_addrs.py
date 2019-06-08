from django.core.management.base import BaseCommand
from mailer.models import Message
from members.models import Member


class Command(BaseCommand):
    help = 'Shows reply-to addresses'

    def add_arguments(self, parser):
        parser.add_argument('message_id', type=int)

    def handle(self, *args, **options):
        replies = []
        try:
            message = Message.objects.get(pk=options['message_id'])
            if message.reply_to:
                replies = message.reply_to.all()
        except Message.DoesNotExist:
            pass

        if not replies:
            # send mail to all jugendleiters
            replies = Member.objects.filter(group__name='Jugendleiter',
                                            gets_newsletter=True)
        response = "\n".join([l.email for l in replies])
        self.stdout.write(response)
