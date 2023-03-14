from celery import shared_task
from django.utils import timezone
from django.conf import settings
from .models import MemberWaitingList

@shared_task
def ask_for_waiting_confirmation():
    cutoff = timezone.now() - timezone.timedelta(days=settings.WAITING_CONFIRMATION_FREQUENCY)
    for waiter in MemberWaitingList.objects.filter(last_wait_confirmation__lte=cutoff):
        waiter.ask_for_wait_confirmation()
