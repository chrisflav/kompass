from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.http import HttpResponseRedirect
from django.forms import ModelForm, TextInput, DateInput
from members.models import Member
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
