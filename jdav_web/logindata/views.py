from django import forms
from django.shortcuts import render
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.contrib.auth.forms import UserCreationForm
from members.models import Member
from .models import initial_user_setup, RegistrationPassword


def render_register_password(request, key, member, error_message=''):
    return render(request, 'logindata/register_password.html',
                  context={'key': key,
                           'member': member,
                           'error_message': error_message})


def render_register_failed(request):
    return render(request, 'logindata/register_failed.html')


def render_register_form(request, key, password, member, form):
    return render(request, 'logindata/register_form.html',
                  context={'key': key,
                           'password': password,
                           'member': member,
                           'form': form})


def render_register_success(request):
    return render(request, 'logindata/register_success.html')


# Create your views here.
def register(request):
    if request.method == 'GET' and 'key' not in request.GET:
        return HttpResponseRedirect(reverse('startpage:index'))
    if request.method == 'POST' and 'key' not in request.POST:
        return HttpResponseRedirect(reverse('startpage:index'))

    key = request.GET['key'] if request.method == 'GET' else request.POST['key']
    if not key:
        return render_register_failed(request)
    try:
        member = Member.objects.get(invite_as_user_key=key)
    except (Member.DoesNotExist, Member.MultipleObjectsReturned):
        return render_register_failed(request)

    if request.method == 'GET':
        return render_register_password(request, request.GET['key'], member)

    if 'password' not in request.POST:
        return render_register_failed(request)

    password = request.POST['password']

    # check if the entered password is one of the active registration passwords
    if RegistrationPassword.objects.filter(password=password).count() == 0:
        return render_register_password(request, key, member, error_message=_('You entered a wrong password.'))

    if "save" in request.POST:
        form = UserCreationForm(request.POST)
        if not form.is_valid():
            # form is invalid, reprint form with (automatic) error messages
            return render_register_form(request, key, password, member, form)
        user = form.save(commit=False)
        success = initial_user_setup(user, member)
        if success:
            return render_register_success(request)
        else:
            return render_register_failed(request)
    else:
        prefill = {
            'username': '{prename}.{lastname}'.format(prename=member.prename.lower(), lastname=member.lastname.lower())        }
        form = UserCreationForm(initial=prefill)
        return render_register_form(request, key, password, member, form)
