from celery import shared_task

from . import services


@shared_task
def send_material_notices():
    """Once a day: decline unanswered requests, ask holders for reserved pieces, remind borrowers."""
    return services.send_notices()
