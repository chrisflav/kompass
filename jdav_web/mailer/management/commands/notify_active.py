from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.translation import gettext_lazy as _
from mailer.mailutils import send
from members.models import annotate_activity_score
from members.models import Member


class Command(BaseCommand):
    help = "Congratulates the most active members"
    requires_system_checks = False

    def handle(self, *args, **options):
        qs = list(
            reversed(annotate_activity_score(Member.objects.all()).order_by("_activity_score"))
        )[: settings.CONGRATULATE_MEMBERS_MAX]
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
            content = settings.NOTIFY_MOST_ACTIVE_TEXT.format(
                name=member.prename,
                congratulate_max=settings.CONGRATULATE_MEMBERS_MAX,
                score=score,
                level=level,
                position=positiontext,
            )
            send(
                _("Congratulation %(name)s") % {"name": member.prename},
                content,
                settings.DEFAULT_SENDING_ADDRESS,
                [member.email],
                reply_to=[settings.RESPONSIBLE_MAIL],
            )
