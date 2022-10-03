from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.http import HttpResponseRedirect
from django.forms import ModelForm, TextInput, DateInput
from members.models import Member, RegistrationPassword
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

class MemberFormWithEmail(ModelForm):
    class Meta:
        model = Member
        fields = ['prename', 'lastname', 'street', 'plz', 'town', 'phone_number',
                  'phone_number_parents', 'birth_date', 'email', 'email_parents', 'cc_email_parents']
        widgets = {
            'birth_date': DateInput(format='%d.%m.%Y', attrs={'class': 'datepicker'})
        }

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


def render_register_success(request, groupname, membername):
    return render(request,
                  'members/register_success.html',
                  {'groupname': groupname,
                   'membername': membername})


def render_register(request, pwd, form=None):
    if form is None:
        form = MemberFormWithEmail()
    return render(request,
                  'members/register.html',
                  {'form': form, 'pwd': pwd})


def register(request):
    if request.method == 'GET' or not "password" in request.POST:
        # show password
        return render_register_password(request)
    # confirm password
    try:
        pwd = RegistrationPassword.objects.get(password=request.POST['password'])
    except RegistrationPassword.DoesNotExist:
        return render_register_wrong_password(request)
    if "save" in request.POST:
        # process registration
        form = MemberFormWithEmail(request.POST)
        try:
            new_member = form.save()
            new_member.group.add(pwd.group)
            new_member.confirmed = False
            new_member.save()
            new_member.request_mail_confirmation()
            return render_register_success(request, pwd.group.name, new_member.prename)
        except ValueError:
            # when input is invalid
            return render_register(request, pwd, form)
    # we are not saving yet
    return render_register(request, pwd, form=None)


def confirm_mail(request):
    if request.method == 'GET' and 'key' in request.GET:
        key = request.GET['key']
        res = Member.objects.filter(confirm_mail_key=key) | Member.objects.filter(confirm_mail_parents_key=key)
        if len(res) != 1:
            return render_mail_confirmation_invalid(request)
        member = res[0]
        email, parents = member.confirm_mail(key)
        return render_mail_confirmation_success(request, email, member.prename, parents)
    return HttpResponseRedirect(reverse('startpage:index'))


def render_mail_confirmation_invalid(request):
    return render(request, 'members/mail_confirmation_invalid.html')


def render_mail_confirmation_success(request, email, name, parents=False):
    return render(request, 'members/mail_confirmation_success.html',
                  {'email': email, 'name': name, 'parents': parents})
