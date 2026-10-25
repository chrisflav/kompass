from celery import shared_task

from . import services


@shared_task
def send_material_notices():
    """Once a day: decline unanswered requests, ask holders for reserved pieces, remind borrowers.

    Also asks holders of PSA due for inspection to hand it in.
    """
    return services.send_notices()
