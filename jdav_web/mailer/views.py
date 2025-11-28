from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from members.models import Member

from .mailutils import get_unsubscribe_link
from .mailutils import send as send_mail


def index(request):
    return HttpResponseRedirect(reverse("mailer:unsubscribe"))


def render_unsubscribe(request, error_message=""):
    context = {}
    if error_message:
        context["error_message"] = error_message
    return render(request, "mailer/unsubscribe.html", context)


def render_unsubscribed(request, email):
    return render(request, "mailer/unsubscribed.html", {"email": email})


def unsubscribe(request):
    if request.method == "GET" and "key" in request.GET:
        try:
            key = request.GET["key"]
            member = Member.objects.get(unsubscribe_key=key)
            if not member.unsubscribe(key):
                raise KeyError
        except (KeyError, Member.DoesNotExist):
            return render_unsubscribe(request, _("Can't verify this link. Try again!"))
        else:
            return render_unsubscribed(request, member.email)
    elif not request.POST.get("post", False):
        # just calling up unsubscribe page
        return render_unsubscribe(request)
    try:
        email = request.POST["email"]
        member = Member.objects.filter(email=email).first()
        if not member:  # member not found
            raise KeyError
    except (KeyError, Member.DoesNotExist):
        return render_unsubscribe(request, _("Please fill in every field"))
    else:
        send_mail(
            _("Unsubscription confirmation"),
            settings.UNSUBSCRIBE_CONFIRMATION_TEXT.format(link=get_unsubscribe_link(member)),
            settings.DEFAULT_SENDING_MAIL,
            email,
        )
        return render_confirmation_sent(request, email)


def render_confirmation_sent(request, email):
    return render(request, "mailer/confirmation_sent.html", {"email": email})
