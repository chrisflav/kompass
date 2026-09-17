import logging

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import Freizeit
from .models import MemberWaitingList

logger = logging.getLogger(__name__)


@shared_task
def ask_for_waiting_confirmation():
    reminder_cutoff = timezone.now() - timezone.timedelta(
        days=settings.CONFIRMATION_REMINDER_FREQUENCY
    )
    cutoff = timezone.now() - timezone.timedelta(days=settings.WAITING_CONFIRMATION_FREQUENCY)
    no = 0
    # we ask all waiters for wait confirmation whose last confirmed waiting status is at least
    # settings.WAITING_CONFIRMATION_FREQUENCY days ago, who have not received a reminder
    # in the last settings.CONFIRMATION_REMINDER_FREQUENCY days and
    # who have yet received strictly less reminders then settings.MAX_REMINDER_COUNT.
    for waiter in MemberWaitingList.objects.filter(
        last_wait_confirmation__lte=cutoff,
        last_reminder__lte=reminder_cutoff,
        sent_reminders__lt=settings.MAX_REMINDER_COUNT,
    ):
        waiter.ask_for_wait_confirmation()
        no += 1
    return no


@shared_task(autoretry_for=(Exception,), retry_backoff=60, max_retries=3)
def send_crisis_intervention_list():
    """
    Send crisis intervention lists for all excursions that start on the current day and
    that have not been sent yet.

    One excursion failing must not cost the others their list, so failures are collected
    and only raised once every excursion has been attempted. Retrying is worthwhile
    because an excursion leaves the queryset as soon as it starts: a list that fails at
    night is not picked up by the next nightly run. The backoff spans minutes rather
    than seconds so that a short mail or broker outage is survived. Excursions that did
    go out are already marked as sent, so a retry only reattempts the ones that failed.
    """
    no = 0
    failed = []
    for excursion in Freizeit.to_send_crisis_intervention_list():
        try:
            excursion.send_crisis_intervention_list()
        except Exception:
            logger.exception(
                "Could not send the crisis intervention list for excursion %s.", excursion.code
            )
            failed.append(excursion.code)
        else:
            no += 1
    if failed:
        raise RuntimeError(
            "Could not send crisis intervention lists for: {}".format(", ".join(failed))
        )
    return no


@shared_task
def send_notification_crisis_intervention_list():
    """
    Send crisis intervention list notifiactions for all excursions that start on the next
    day and that have not been sent yet.
    """
    no = 0
    for excursion in Freizeit.to_notify_crisis_intervention_list():
        excursion.notify_leaders_crisis_intervention_list()
        no += 1
    return no
