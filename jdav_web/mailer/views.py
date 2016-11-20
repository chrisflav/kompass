from django.shortcuts import render
from django import forms
from django.utils.translation import ugettext_lazy as _
from django.urls import reverse
from django.http import HttpResponseRedirect

from members.models import Member


def index(request):
    return HttpResponseRedirect(reverse('mailer:subscribe'))


def render_subscribe(request, error_message=""):
    date_input = forms.DateInput(attrs={'required': True,
                                        'class': 'datepicker',
                                        'name': 'birthdate'})
    date_field = date_input.render(_("Birthdate"), "")
    context = {'date_field': date_field}
    if error_message:
        context['error_message'] = error_message
    return render(request, 'mailer/subscribe.html', context)


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
                                        error_message=_("Member already exists"))
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
