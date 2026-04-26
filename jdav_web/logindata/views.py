from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.forms import UserCreationForm
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from members.models import Member

from .models import initial_user_setup
from .models import RegistrationPassword


def render_register_password(request, key, member, is_reset_mode=False, error_message=""):
    return render(
        request,
        "logindata/register_password.html",
        context={
            "key": key,
            "member": member,
            "is_reset_mode": is_reset_mode,
            "error_message": error_message,
        },
    )


def render_register_failed(request):
    return render(request, "logindata/register_failed.html")


def render_register_form(request, key, password, member, form, is_reset_mode=False):
    return render(
        request,
        "logindata/register_form.html",
        context={
            "key": key,
            "password": password,
            "member": member,
            "form": form,
            "is_reset_mode": is_reset_mode,
        },
    )


def render_register_success(request, is_reset_mode=False):
    return render(
        request,
        "logindata/register_success.html",
        context={"is_reset_mode": is_reset_mode},
    )


# Create your views here.
def register(request):
    if request.method == "GET" and "key" not in request.GET:
        return HttpResponseRedirect(reverse("startpage:index"))
    if request.method == "POST" and "key" not in request.POST:
        return HttpResponseRedirect(reverse("startpage:index"))

    key = request.GET["key"] if request.method == "GET" else request.POST["key"]
    if not key:
        return render_register_failed(request)
    try:
        member = Member.objects.get(invite_as_user_key=key)
    except (Member.DoesNotExist, Member.MultipleObjectsReturned):
        return render_register_failed(request)

    is_reset_mode = bool(member.user)

    if request.method == "GET":
        return render_register_password(request, request.GET["key"], member, is_reset_mode)

    if "password" not in request.POST:
        return render_register_failed(request)

    password = request.POST["password"]

    # check if the entered password is one of the active registration passwords
    if RegistrationPassword.objects.filter(password=password).count() == 0:
        return render_register_password(
            request, key, member, is_reset_mode, error_message=_("You entered a wrong password.")
        )

    if "save" in request.POST:
        if is_reset_mode:
            # Password reset: use SetPasswordForm
            form = SetPasswordForm(member.user, request.POST)
            if not form.is_valid():
                return render_register_form(request, key, password, member, form, is_reset_mode)
            form.save()
            member.invite_as_user_key = ""
            member.save()
            return render_register_success(request, is_reset_mode)
        else:
            # New user registration
            form = UserCreationForm(request.POST)
            if not form.is_valid():
                return render_register_form(request, key, password, member, form, is_reset_mode)
            user = form.save(commit=False)
            success = initial_user_setup(user, member)
            if success:
                return render_register_success(request, is_reset_mode)
            else:
                return render_register_failed(request)
    else:
        if is_reset_mode:
            form = SetPasswordForm(member.user)
        else:
            prefill = {"username": member.suggested_username()}
            form = UserCreationForm(initial=prefill)
        return render_register_form(request, key, password, member, form, is_reset_mode)
