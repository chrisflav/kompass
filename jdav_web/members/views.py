from startpage.views import render
from django.utils.translation import gettext_lazy as _
from django.http import HttpResponseRedirect
from django.forms import ModelForm, TextInput, DateInput, BaseInlineFormSet,\
    inlineformset_factory, HiddenInput
from members.models import Member, RegistrationPassword, MemberUnconfirmedProxy, MemberWaitingList, Group,\
    confirm_mail_by_key, EmergencyContact
from django.urls import reverse
from django.utils import timezone
from django.conf import settings


class MemberForm(ModelForm):
    class Meta:
        model = Member
        fields = ['prename', 'lastname', 'street', 'plz', 'town', 'address_extra', 'country',
                  'phone_number']

class MemberRegistrationForm(ModelForm):
    def __init__(self, *args, **kwargs):
        super(MemberRegistrationForm, self).__init__(*args, **kwargs)

        for field in self.Meta.required:
            self.fields[field].required = True

    class Meta:
        model = Member
        fields = ['prename', 'lastname', 'street', 'plz', 'town', 'address_extra', 'country',
                  'phone_number', 'birth_date', 'gender', 'email', 'alternative_email',
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

    class Meta:
        model = MemberWaitingList
        fields = ['prename', 'lastname', 'birth_date', 'gender', 'email', 'application_text']
        widgets = {
            'birth_date': DateInput(format='%d.%m.%Y', attrs={'class': 'datepicker'})
        }
        required = []


class EmergencyContactForm(ModelForm):
    def __init__(self, *args, **kwargs):
        super(EmergencyContactForm, self).__init__(*args, **kwargs)

        for field in self.Meta.required:
            self.fields[field].widget.attrs['required'] = 'required'

    class Meta:
        model = EmergencyContact
        fields = ['prename', 'lastname', 'email', 'phone_number']
        required = ['prename', 'lastname', 'email', 'phone_number']


class BaseEmergencyContactsFormSet(BaseInlineFormSet):
    deletion_widget = HiddenInput


EmergencyContactsFormSet = inlineformset_factory(Member, EmergencyContact,
    form=EmergencyContactForm, fields=['prename', 'lastname', 'email', 'phone_number'],
    extra=0, min_num=1,
    can_delete=True, can_delete_extra=True, validate_min=True,
    formset=BaseEmergencyContactsFormSet)


def render_echo_password(request, key):
    return render(request, 'members/echo_password.html',
                  context={'key': key})


def render_echo_wrong_password(request, key):
    return render(request,
                  'members/echo_password.html',
                  {'error_message': _("The entered password is wrong."),
                   'key': key})


def render_echo_failed(request, reason=""):
    context = {}
    if reason:
        context['reason'] = reason
    return render(request, 'members/echo_failed.html', context)


def render_echo(request, key, password, form, emergency_contacts_formset):
    return render(request, 'members/echo.html',
            {'form': form.as_table(),
             'emergency_contacts_formset': emergency_contacts_formset,
             'key' : key,
             'registration': False,
             'password': password})


def render_echo_success(request, name):
    return render(request, 'members/echo_success.html', {'name': name})


def echo(request):
    if request.method == 'GET' and 'key' not in request.GET:
        # invalid
        return HttpResponseRedirect(reverse('startpage:index'))

    if request.method == 'GET':
        # show password
        return render_echo_password(request, request.GET['key'])

    if 'password' not in request.POST or 'key' not in request.POST:
        return render_echo_failed(request, _("invalid"))

    key = request.POST['key']
    password = request.POST['password']
    # try to get a member from the supplied echo key
    try:
        member = Member.objects.get(echo_key=key)
    except Member.DoesNotExist:
        return render_echo_failed(request, _("invalid"))
    # check if echo key is not expired
    if not member.may_echo(key):
        return render_echo_failed(request, _("expired"))
    # check password
    if password != member.echo_password:
        return render_echo_wrong_password(request, key)
    if "save" in request.POST:
        form = MemberForm(request.POST, instance=member)
        emergency_contacts_formset = EmergencyContactsFormSet(request.POST, instance=member)
        try:
            if not emergency_contacts_formset.is_valid():
                raise ValueError(_("Invalid emergency contacts"))
            form.save()
            emergency_contacts_formset.save()
            member.echo_key, member.echo_expire = "", timezone.now()
            member.echoed = True
            member.save()
            return render_echo_success(request, member.prename)
        except ValueError:
            # when input is invalid
            form = MemberForm(request.POST)
            emergency_contacts_formset = EmergencyContactsFormSet(request.POST)
            return render_echo(request, key, password, form, emergency_contacts_formset)
    else:
        form = MemberForm(instance=member)
        emergency_contacts_formset = EmergencyContactsFormSet(instance=member)
        return render_echo(request, key, password, form, emergency_contacts_formset)


def render_register_password(request):
    return render(request, 'members/register_password.html',
                  context={'sektion': settings.SEKTION})


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


def render_register(request, group, form=None, emergency_contacts_formset=None,
        pwd=None, waiter_key=''):
    if form is None:
        form = MemberRegistrationForm()
    if emergency_contacts_formset is None:
        emergency_contacts_formset = EmergencyContactsFormSet()
    return render(request,
                  'members/register.html',
                  {'form': form,
                   'emergency_contacts_formset': emergency_contacts_formset,
                   'group': group,
                   'waiter_key': waiter_key,
                   'pwd': pwd,
                   'sektion': settings.SEKTION,
                   'registration': True
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
        emergency_contacts_formset = EmergencyContactsFormSet(request.POST)
        try:
            # first try to save member
            new_member = form.save(commit=False)
            # then instantiate emergency contacts with this member
            emergency_contacts_formset.instance = new_member
            if emergency_contacts_formset.is_valid():
                # if emergency contacts are valid, save new_member and save emergency contacts
                new_member.save()
                emergency_contacts_formset.save()
            else:
                raise ValueError
            needs_mail_confirmation = new_member.create_from_registration(waiter, group)
            return render_register_success(request, group.name, new_member.prename, needs_mail_confirmation)
        except ValueError as e:
            print("value error", e)
            # when input is invalid
            return render_register(request, group, form, emergency_contacts_formset, pwd=pwd.password,
                    waiter_key=waiter_key)
    # we are not saving yet
    return render_register(request, group, form=None, pwd=pwd.password, waiter_key=waiter_key)


def confirm_mail(request):
    if request.method == 'GET' and 'key' in request.GET:
        res = confirm_mail_by_key(request.GET['key'])
        if res:
            return render_mail_confirmation_success(request, res[1], res[0].prename, False)
        else:
            return render_mail_confirmation_invalid(request)
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
                  {'form': form, 'sektion': settings.SEKTION })


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
