from django.core.management.base import BaseCommand
from members.models import Member
from django.db.models import Q

import re


class Command(BaseCommand):
    help = 'Parses an email address and finds the associated jugendleiter'
    requires_system_checks = False

    def add_arguments(self, parser):
        parser.add_argument('--name', default="")

    def handle(self, *args, **options):
        match = re.match('([A-Za-z0-9]*)[ ._-]*(.*)', options['name'])
        if not match:
            return
        prename, lastname = match.groups()
        try:
            jugendleiter = Member.objects.filter(group__name='Jugendleiter')
            matching = [jl.email for jl in jugendleiter if matches(jl.prename.lower(),
                                                                   jl.lastname.lower(),
                                                                   prename.lower(),
                                                                   lastname.lower())]
            if not matching:
                return
            self.stdout.write(" ".join(matching))
        except Member.DoesNotExist:
            pass


def matches(prename, lastname, matched_pre, matched_last):
    if not matched_last and matched_pre and len(matched_pre) > 2:
        return prename.startswith(matched_pre) or lastname.startswith(matched_pre)
    if matched_pre and matched_last:
        return (prename.startswith(matched_pre) and lastname.startswith(matched_last)) or (prename.startswith(matched_last) and lastname.startswith(matched_pre))
    return False
