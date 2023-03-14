from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.http import HttpResponseRedirect
from django.forms import ModelForm, TextInput, DateInput
from members.models import Member, RegistrationPassword, MemberUnconfirmedProxy, MemberWaitingList, Group
from django.urls import reverse
from django.utils import timezone


class MemberForm(ModelForm):
    class Meta:
        model = Member
        fields = ['prename', 'lastname', 'street', 'plz', 'town', 'phone_number',
                  'phone_number_parents', 'birth_date']
        widgets = {
            'birth_date': DateInput(format='%d.%m.%Y', attrs={'class': 'datepicker'})
        }

class MemberRegistrationForm(ModelForm):
    def __init__(self, *args, **kwargs):
        super(MemberRegistrationForm, self).__init__(*args, **kwargs)

        for field in self.Meta.required:
            self.fields[field].required = True

        self.fields['cc_email_parents'].initial = False

    class Meta:
        model = Member
        fields = ['prename', 'lastname', 'street', 'plz', 'town', 'phone_number',
                  'phone_number_parents', 'birth_date', 'email', 'email_parents', 'cc_email_parents',
                  'registration_form']
        widgets = {
            'birth_date': DateInput(format='%d.%m.%Y', attrs={'class': 'datepicker'})
        }
        required = ['registration_form', 'street', 'plz', 'town']


class MemberRegistrationWaitingListForm(ModelForm):
    def __init__(self, *args, **kwargs):
        super(MemberRegistrationWaitingListForm, self).__init__(*args, **kwargs)

        for field in self.Meta.required:
            self.fields[field].required = True

        self.fields['cc_email_parents'].initial = False

    class Meta:
        model = MemberWaitingList
        fields = ['prename', 'lastname', 'birth_date', 'email', 'email_parents', 'cc_email_parents']
        widgets = {
            'birth_date': DateInput(format='%d.%m.%Y', attrs={'class': 'datepicker'})
        }
        required = []


def render_echo_failed(request, reason=""):
    context = {}
    if reason:
        context['reason'] = reason
    return render(request, 'members/echo_failed.html', context)


def render_echo(request, key, form):
    return render(request, 'members/echo.html', {'form': form.as_table(),
                                                 'key' : key})


def render_echo_success(request, name):
    return render(request, 'members/echo_success.html', {'name': name})


def echo(request):
    if request.method == 'GET' and 'key' in request.GET:
        try:
            key = request.GET['key']
            member = Member.objects.get(echo_key=key)
            if not member.may_echo(key):
                raise KeyError
            form = MemberForm(instance=member)
            return render_echo(request, key, form)
        except Member.DoesNotExist:
            return render_echo_failed(request, _("invalid"))
        except KeyError:
            return render_echo_failed(request, _("expired"))
    elif request.method == 'POST':
        try:
            key = request.POST['key']
            member = Member.objects.get(echo_key=key)
            if not member.may_echo(key):
                raise KeyError
            form = MemberForm(request.POST, instance=member)
            try:
                form.save()
                member.echo_key, member.echo_expire = "", timezone.now()
                member.echoed = True
                member.save()
                return render_echo_success(request, member.prename)
            except ValueError:
                # when input is invalid
                form = MemberForm(request.POST)
                return render_echo(request, key, form)
        except (Member.DoesNotExist, KeyError):
            return render_echo_failed(request, _("invalid"))


def render_register_password(request):
    return render(request, 'members/register_password.html')


def render_register_wrong_password(request):
    return render(request,
                  'members/register_password.html',
                  {'error_message': _("The entered password is wrong.")})


def render_register_success(request, groupname, membername, needs_mail_confirmation):
    return render(request,
                  'members/register_success.html',
                  {'groupname': groupname,
                   'membername': membername,
                   'needs_mail_confirmation': needs_mail_confirmation})


def render_register(request, group, form=None, pwd=None, waiter_key=''):
    if form is None:
        form = MemberRegistrationForm()
    return render(request,
                  'members/register.html',
                  {'form': form,
                   'group': group,
                   'waiter_key': waiter_key,
                   'pwd': pwd,
                  })


def render_register_failed(request, reason=""):
    context = {}
    if reason:
        context['reason'] = reason
    return render(request, 'members/register_failed.html', context)


def register(request):
    if request.method == 'GET' or ("password" not in request.POST and "waiter_key" not in request.POST):
        # show password
        return render_register_password(request)

    # find group and potential waiter
    group = None
    waiter = None
    pwd = None
    waiter_key = request.POST['waiter_key'] if 'waiter_key' in request.POST else ''
    if "password" in request.POST and request.POST['password']:
        # confirm password
        try:
            pwd = RegistrationPassword.objects.get(password=request.POST['password'])
            group = pwd.group
        except RegistrationPassword.DoesNotExist:
            return render_register_wrong_password(request)
    elif waiter_key: 
        try:
            waiter = MemberWaitingList.objects.get(registration_key=waiter_key)
            group = waiter.invited_for_group
        except MemberWaitingList.DoesNotExist:
            return render_register_failed(request)

    # group must not be None
    if group is None:
        return render_register_failed(request)

    if "save" in request.POST:
        # process registration
        form = MemberRegistrationForm(request.POST, request.FILES)
        try:
            new_member = form.save()
            new_member.group.add(group)
            new_member.confirmed = False
            needs_mail_confirmation = True
            if waiter:
                if new_member.email == waiter.email and new_member.email_parents == waiter.email_parents:
                    new_member.confirmed_mail = True
                    new_member.confirmed_mail_parents = True
                    needs_mail_confirmation = False
                    new_member.notify_jugendleiters_about_confirmed_mail()
                waiter.delete()

            new_member.save()
            if needs_mail_confirmation:
                new_member.request_mail_confirmation()
            return render_register_success(request, group.name, new_member.prename, needs_mail_confirmation)
        except ValueError:
            # when input is invalid
            return render_register(request, group, form, pwd=pwd, waiter_key=waiter_key)
    # we are not saving yet
    return render_register(request, group, form=None, pwd=pwd, waiter_key=waiter_key)


def confirm_mail(request):
    if request.method == 'GET' and 'key' in request.GET:
        key = request.GET['key']
        matching_unconfirmed = MemberUnconfirmedProxy.objects.filter(confirm_mail_key=key) \
                             | MemberUnconfirmedProxy.objects.filter(confirm_mail_parents_key=key)
        matching_waiter = MemberWaitingList.objects.filter(confirm_mail_key=key) \
                        | MemberWaitingList.objects.filter(confirm_mail_parents_key=key)
        if len(matching_unconfirmed) + len(matching_waiter) != 1:
            return render_mail_confirmation_invalid(request)
        person = matching_unconfirmed[0] if len(matching_unconfirmed) == 1 else matching_waiter[0]
        email, parents = person.confirm_mail(key)
        return render_mail_confirmation_success(request, email, person.prename, parents)
    return HttpResponseRedirect(reverse('startpage:index'))


def render_mail_confirmation_invalid(request):
    return render(request, 'members/mail_confirmation_invalid.html')


def render_mail_confirmation_success(request, email, name, parents=False):
    return render(request, 'members/mail_confirmation_success.html',
                  {'email': email, 'name': name, 'parents': parents})


def render_register_waiting_list(request, form=None):
    if form is None:
        form = MemberRegistrationWaitingListForm()
    return render(request,
                  'members/register_waiting_list.html',
                  {'form': form})


def render_register_waiting_list_success(request, membername):
    return render(request,
                  'members/register_waiting_list_success.html',
                  {'membername': membername})


def register_waiting_list(request):
    if request.method == 'GET':
        # ask to fill in form
        return render_register_waiting_list(request)
    if "save" in request.POST:
        # process registration for waiting list
        form = MemberRegistrationWaitingListForm(request.POST, request.FILES)
        try:
            new_waiter = form.save()
            new_waiter.save()
            new_waiter.request_mail_confirmation()
            return render_register_waiting_list_success(request, new_waiter.prename)
        except ValueError:
            # when input is invalid
            return render_register_waiting_list(request, form)
    # we are not saving yet
    return render_register_waiting_list(request, form=None)


def invited_registration(request):
    if request.method == 'GET' and 'key' in request.GET:
        try:
            key = request.GET['key']
            waiter = MemberWaitingList.objects.get(registration_key=key)
            if not waiter.may_register(key):
                raise KeyError
            if not waiter.invited_for_group:
                raise KeyError
            form = MemberRegistrationForm(instance=waiter)
            return render_register(request, group=waiter.invited_for_group, form=form, waiter_key=key)
        except MemberWaitingList.DoesNotExist:
            return render_invited_registration_failed(request, _("invalid"))
        except KeyError:
            return render_invited_registration_failed(request, _("expired"))
    
    # if its a POST request
    return register(request)


def render_invited_registration_failed(request, reason=""):
    context = {}
    if reason:
        context['reason'] = reason
    return render(request, 'members/invited_registration_failed.html', context)


def confirm_waiting(request):
    if request.method == 'GET' and 'key' in request.GET:
        key = request.GET['key']
        try:
            waiter = MemberWaitingList.objects.get(wait_confirmation_key=key)
        except MemberWaitingList.DoesNotExist:
            return render_waiting_confirmation_invalid(request)
        status = waiter.confirm_waiting(key)
        if status == MemberWaitingList.WAITING_CONFIRMATION_SUCCESS:
            return render_waiting_confirmation_success(request,
                                                       waiter.prename,
                                                       already_confirmed=False)
        elif status == MemberWaitingList.WAITING_CONFIRMED:
            return render_waiting_confirmation_success(request,
                                                       waiter.prename,
                                                       already_confirmed=True)
        elif status == MemberWaitingList.WAITING_CONFIRMATION_EXPIRED:
            return render_waiting_confirmation_invalid(request, prename=waiter.prename, expired=True)
        else:
            # invalid
            return render_waiting_confirmation_invalid(request)
    return HttpResponseRedirect(reverse('startpage:index'))


def render_waiting_confirmation_invalid(request, prename=None, expired=False):
    return render(request,
                  'members/waiting_confirmation_invalid.html',
                  {'expired': expired, 'prename': prename})


def render_waiting_confirmation_success(request, prename, already_confirmed):
    return render(request, 'members/waiting_confirmation_success.html',
                  {'prename': prename, 'already_confirmed': already_confirmed})
