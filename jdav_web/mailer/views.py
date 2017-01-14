from django.shortcuts import render
from django import forms
from django.utils.translation import ugettext_lazy as _
from django.urls import reverse
from django.http import HttpResponseRedirect
from .mailutils import send as send_mail, mail_root, get_unsubscribe_link

from members.models import Member


def index(request):
    return HttpResponseRedirect(reverse('mailer:unsubscribe'))


def render_unsubscribe(request, error_message=""):
    context = {}
    if error_message:
        context['error_message'] = error_message
    return render(request, 'mailer/unsubscribe.html', context)


def render_unsubscribed(request, email):
    return render(request, 'mailer/unsubscribed.html', {'email': email})


def unsubscribe(request):
    if request.method == 'GET' and 'key' in request.GET:
        try:
            key = request.GET['key']
            member = Member.objects.get(unsubscribe_key=key)
            if not member.unsubscribe(key):
                raise KeyError
        except (KeyError, Member.DoesNotExist):
            return render_unsubscribe(request,
                                      _("Can't verify this link. Try again!"))
        else:
            return render_unsubscribed(request, member.email)
    elif not request.POST.get('post', False):
        # just calling up unsubscribe page
        return render_unsubscribe(request)
    try:
        email = request.POST['email']
        member = Member.objects.filter(email=email).first()
        if not member:  # member not found
            raise KeyError
    except (KeyError, Member.DoesNotExist):
        return render_unsubscribe(request, _("Please fill in every field"))
    else:
        send_mail("Abmeldebestätigung",
                  "Klicke auf den Link, um dich vom Newsletter des JDAV "
                  "Ludwigsburg "
                  "abzumelden\n{}".format(get_unsubscribe_link(member)),
                  mail_root, email)
        return render_confirmation_sent(request, email)


def render_subscribe(request, error_message=""):
    date_input = forms.DateInput(attrs={'required': True,
                                        'class': 'datepicker',
                                        'name': 'birthdate'})
    date_field = date_input.render(_("Birthdate"), "")
    context = {'date_field': date_field}
    if error_message:
        context['error_message'] = error_message
    return render(request, 'mailer/subscribe.html', context)


def render_confirmation_sent(request, email):
    return render(request, 'mailer/confirmation_sent.html', {'email': email})


def subscribe(request):
    try:
        request.POST['post']
        try:
            print("trying to subscribe")
            prename = request.POST['prename']
            lastname = request.POST['lastname']
            email = request.POST['email']
            print("email", email)
            birth_date = request.POST['birthdate']
            print("birthdate", birth_date)
        except KeyError:
            return subscribe(request, _("Please fill in every field!"))
        else:
            # TODO: check whether member exists
            exists = Member.objects.filter(prename=prename,
                                           lastname=lastname)
            if len(exists) > 0:
                return render_subscribe(request,
                                        error_message=_("Member "
                                                        "already exists"))
            member = Member(prename=prename,
                            lastname=lastname,
                            email=email,
                            birth_date=birth_date,
                            gets_newsletter=True)
            member.save()
            return subscribed(request)
    except KeyError:
        return render_subscribe(request)


def subscribed(request):
    return render(request, 'mailer/subscribed.html')
