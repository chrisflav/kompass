from django.core.management.base import BaseCommand
from mailer.models import Message
from members.models import Member, annotate_activity_score
from django.db.models import Q
from mailer.mailutils import mail_root, send

import re

CONGRATULATE_MEMBERS_MAX = 10
SENDING_ADDRESS = mail_root


class Command(BaseCommand):
    help = 'Congratulates the most active members'
    requires_system_checks = False

    def handle(self, *args, **options):
        qs = list(reversed(annotate_activity_score(Member.objects.all()).order_by('_activity_score')))[:CONGRATULATE_MEMBERS_MAX]
        for position, member in enumerate(qs):
            positiontext = "{}. ".format(position + 1) if position > 0 else ""
            score = member._activity_score
            if score < 5:
                level = 1
            elif score >= 5 and score < 10:
                level = 2
            elif score >= 10 and score < 20:
                level = 3
            elif score >= 20 and score < 30:
                level = 4
            else:
                level = 5
            print("sent to ", member.prename)
            content = "Hallo {}!\n\n"\
                "Herzlichen Glückwunsch, du hast im letzten Jahr zu den {} aktivsten "\
                "Mitgliedern der JDAV Ludwigsburg gehört! Um genau zu sein beträgt "\
                "dein Aktivitäts Wert "\
                "des letzten Jahres {} Punkte. Das entspricht {} Kletterer*innen. "\
                "Damit warst du im letzten Jahr "\
                "das {}aktivste Mitglied der JDAV Ludwigsburg.\n\n"\
                "Auf ein weiteres aktives Jahr in der JDAV Ludwigsburg\n"\
                "Dein*e Jugendreferent*in".format(member.prename,
                                                  CONGRATULATE_MEMBERS_MAX,
                                                  score,
                                                  level,
                                                  positiontext)
            send("Herzlichen Glückwunsch {}".format(member.prename),
                 content, SENDING_ADDRESS, [member.email],
                 reply_to=["jugendreferent@jdav-ludwigsburg.de"])
