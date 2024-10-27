from celery import shared_task
from django.utils import timezone
from django.conf import settings
from .models import MemberWaitingList

@shared_task
def ask_for_waiting_confirmation():
    reminder_cutoff = timezone.now() - timezone.timedelta(days=settings.CONFIRMATION_REMINDER_FREQUENCY)
    cutoff = timezone.now() - timezone.timedelta(days=settings.WAITING_CONFIRMATION_FREQUENCY)
    no = 0
    # we ask all waiters for wait confirmation whose last confirmed waiting status is at least
    # settings.WAITING_CONFIRMATION_FREQUENCY days ago, who have not received a reminder
    # in the last settings.CONFIRMATION_REMINDER_FREQUENCY days and
    # who have yet received strictly less reminders then settings.MAX_REMINDER_COUNT.
    for waiter in MemberWaitingList.objects.filter(last_wait_confirmation__lte=cutoff,
                                                   last_reminder__lte=reminder_cutoff,
                                                   sent_reminders__lt=settings.MAX_REMINDER_COUNT):
        waiter.ask_for_wait_confirmation()
        no += 1
    return no
