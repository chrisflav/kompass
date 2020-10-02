from django.core.management.base import BaseCommand
from members.models import Member
from mailer.models import EmailAddress

import re


class Command(BaseCommand):
    help = 'Parses an email address and finds the associated jugendleiter'
    requires_system_checks = False

    def add_arguments(self, parser):
        parser.add_argument('--sender', default="")
        # parser.add_argument('--recipient', default="")

    def handle(self, *args, **options):
        #match = re.match('reply-to-(.?*)_.at._(.*)', options['recipient'])
        #if not match:
        #    return
        #name, domain = match.groups()
        #address = "{}@{}".format(name, domain)
        # recipient = Member.objects.filter(email=address)
        sender = Member.objects.filter(group__name='Jugendleiter', email=options['sender']).first()
        if not sender:
            return
        self.stdout.write(sender.association_email)
