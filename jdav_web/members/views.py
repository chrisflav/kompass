from django.conf import settings
from django.forms import BaseInlineFormSet
from django.forms import DateInput
from django.forms import FileInput
from django.forms import HiddenInput
from django.forms import inlineformset_factory
from django.forms import ModelForm
from django.http import Http404
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import never_cache
from members.models import confirm_mail_by_key
from members.models import EmergencyContact
from members.models import InvitationToGroup
from members.models import Member
from members.models import MemberWaitingList
from members.models import RegistrationPassword
from startpage.views import render

from .pdf import render_tex


class MemberForm(ModelForm):
    class Meta:
        model = Member
        fields = [
            "prename",
            "lastname",
            "gender",
            "street",
            "plz",
            "town",
            "address_extra",
            "phone_number",
            "dav_badge_no",
            "photos_may_be_taken",
        ]

        help_texts = {
            "prename": _("Prename of the member."),
            "lastname": _("Lastname of the member."),
            "phone_number": _("phone number of child or parent"),
            "photos_may_be_taken": _("Are we allowed to take photos of you during activities? We use them for our public relations work."),
        }


class MemberRegistrationForm(ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.Meta.required:
            self.fields[field].required = True

    class Meta:
        model = Member
        fields = [
            "prename",
            "lastname",
            "street",
            "plz",
            "town",
            "address_extra",
            "phone_number",
            "birth_date",
            "gender",
            "email",
            "alternative_email",
            "photos_may_be_taken",
        ]
        widgets = {
            "birth_date": DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        }
        help_texts = {
            "prename": _("Prename of the member."),
            "lastname": _("Lastname of the member."),
            "phone_number": _("phone number of child or parent"),
            "email": _("email of child if available, otherwise parental email address"),
            "alternative_email": _("optional additional email address"),
            "photos_may_be_taken": _("Are we allowed to take photos of you during activities? We use them for our public relations work."),
        }
        required = ["street", "plz", "town"]


class UploadRegistrationForm(ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.Meta.required:
            self.fields[field].required = True

    class Meta:
        model = Member
        fields = ["registration_form"]
        widgets = {
            "registration_form": FileInput(
                attrs={"accept": "application/pdf,image/jpeg,image/png"}
            ),
        }
        required = ["registration_form"]


class MemberRegistrationWaitingListForm(ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.Meta.required:
            self.fields[field].required = True

    class Meta:
        model = MemberWaitingList
        fields = ["prename", "lastname", "birth_date", "gender", "email", "application_text"]
        widgets = {"birth_date": DateInput(format="%Y-%m-%d", attrs={"type": "date"})}
        help_texts = {
            "prename": _("Prename of the member."),
            "lastname": _("Lastname of the member."),
        }
        required = ["birth_date"]


class EmergencyContactForm(ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.Meta.required:
            self.fields[field].widget.attrs["required"] = "required"

    class Meta:
        model = EmergencyContact
        fields = ["prename", "lastname", "email", "phone_number"]
        required = ["prename", "lastname", "phone_number"]


class BaseEmergencyContactsFormSet(BaseInlineFormSet):
    deletion_widget = HiddenInput


EmergencyContactsFormSet = inlineformset_factory(
    Member,
    EmergencyContact,
    form=EmergencyContactForm,
    fields=["prename", "lastname", "email", "phone_number"],
    extra=0,
    min_num=1,
    can_delete=True,
    can_delete_extra=True,
    validate_min=True,
    formset=BaseEmergencyContactsFormSet,
)


def render_echo_password(request, key):
    return render(request, "members/echo_password.html", context={"key": key})


def render_echo_wrong_password(request, key):
    return render(
        request,
        "members/echo_password.html",
        {"error_message": _("The entered password is wrong."), "key": key},
    )


def render_echo_failed(request, reason=""):
    context = {}
    if reason:
        context["reason"] = reason
    return render(request, "members/echo_failed.html", context)


def render_echo(request, key, password, form, emergency_contacts_formset):
    return render(
        request,
        "members/echo.html",
        {
            "form": form.as_table(),
            "emergency_contacts_formset": emergency_contacts_formset,
            "key": key,
            "registration": False,
            "password": password,
        },
    )


def render_echo_success(request, name):
    return render(request, "members/echo_success.html", {"name": name})


def echo(request):
    if request.method == "GET" and "key" not in request.GET:
        # invalid
        return HttpResponseRedirect(reverse("startpage:index"))

    if request.method == "GET":
        key = request.GET["key"]
        # try to get a member from the supplied echo key
        try:
            member = Member.objects.get(echo_key=key)
        except Member.DoesNotExist:
            return render_echo_failed(request, _("invalid"))

        # show password
        return render_echo_password(request, request.GET["key"])

    if "password" not in request.POST or "key" not in request.POST:
        return render_echo_failed(request, _("invalid"))

    key = request.POST["key"]
    password = request.POST["password"]
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
            # We don't invalidate the echo key, so the user
            # can echo again if wanted.
            # member.echo_key, member.echo_expire = "", timezone.now()
            member.echoed = True
            member.save()
            if not member.registration_form:
                # If the member does not have a registration form, forward them to the upload page.
                member.request_registration_form()
                return HttpResponseRedirect(
                    reverse("members:upload_registration_form")
                    + "?key="
                    + member.upload_registration_form_key
                )
            else:
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
    return render(request, "members/register_password.html", context={"sektion": settings.SEKTION})


def render_register_wrong_password(request):
    return render(
        request,
        "members/register_password.html",
        {"error_message": _("The entered password is wrong.")},
    )


def render_register_success(request, groupname, membername, needs_mail_confirmation):
    return render(
        request,
        "members/register_success.html",
        {
            "groupname": groupname,
            "membername": membername,
            "needs_mail_confirmation": needs_mail_confirmation,
        },
    )


def render_register(
    request, group, form=None, emergency_contacts_formset=None, pwd="", waiter_key=""
):
    if form is None:
        form = MemberRegistrationForm()
    if emergency_contacts_formset is None:
        emergency_contacts_formset = EmergencyContactsFormSet()
    return render(
        request,
        "members/register.html",
        {
            "form": form,
            "emergency_contacts_formset": emergency_contacts_formset,
            "group": group,
            "waiter_key": waiter_key,
            "password": pwd,
            "sektion": settings.SEKTION,
            "registration": True,
        },
    )


def render_register_failed(request, reason=""):
    context = {}
    if reason:
        context["reason"] = reason
    return render(request, "members/register_failed.html", context)


def register(request):
    if request.method == "GET" or (
        "password" not in request.POST and "waiter_key" not in request.POST
    ):
        # show password
        return render_register_password(request)

    # find group and potential waiter
    group = None
    waiter = None
    pwd = None
    waiter_key = request.POST["waiter_key"] if "waiter_key" in request.POST else ""
    if "password" in request.POST and request.POST["password"]:
        # confirm password
        try:
            pwd = RegistrationPassword.objects.get(password=request.POST["password"])
            group = pwd.group
        except RegistrationPassword.DoesNotExist:
            return render_register_wrong_password(request)
    elif waiter_key:
        try:
            invitation = InvitationToGroup.objects.get(key=waiter_key)
            waiter = invitation.waiter
            group = invitation.group
        except InvitationToGroup.DoesNotExist:
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
            new_member.create_from_registration(waiter, group)
            new_member.send_upload_registration_form_link()
            return HttpResponseRedirect(
                reverse("members:upload_registration_form")
                + "?key="
                + new_member.upload_registration_form_key
            )
        except ValueError:
            # when input is invalid
            if pwd:
                return render_register(
                    request,
                    group,
                    form,
                    emergency_contacts_formset,
                    pwd=pwd.password,
                    waiter_key=waiter_key,
                )
            else:
                return render_register(
                    request, group, form, emergency_contacts_formset, waiter_key=waiter_key
                )
    # we are not saving yet
    if pwd:
        return render_register(request, group, form=None, pwd=pwd.password, waiter_key=waiter_key)
    else:
        return render_register(request, group, form=None, waiter_key=waiter_key)


def render_download_registration_form(request, member):
    context = dict(member=member, settings=settings)
    return render_tex("Anmeldeformular_" + member.name, "members/registration_form.tex", context)


def download_registration_form(request):
    if request.method != "GET" or "key" not in request.GET:
        return render_upload_registration_form_invalid(request)
    key = request.GET["key"]
    try:
        member = Member.all_objects.get(upload_registration_form_key=key)
        return render_download_registration_form(request, member)
    except Member.DoesNotExist:
        return render_upload_registration_form_invalid(request)


def render_upload_registration_form_invalid(request):
    return render(request, "members/upload_registration_form_invalid.html")


def render_upload_registration_form_success(request, member):
    return render(
        request, "members/upload_registration_form_success.html", context={"member": member}
    )


def render_upload_registration_form(request, member, form, key):
    return render(
        request,
        "members/upload_registration_form.html",
        context={"form": form, "member": member, "key": key},
    )


def upload_registration_form(request):
    if request.method == "GET":
        if "key" not in request.GET:
            return render_upload_registration_form_invalid(request)
        key = request.GET["key"]
        try:
            member = Member.all_objects.get(upload_registration_form_key=key)
        except Member.DoesNotExist:
            return render_upload_registration_form_invalid(request)
        form = UploadRegistrationForm(instance=member)
        return render_upload_registration_form(request, member, form, key)
    if "key" not in request.POST:
        return render_upload_registration_form_invalid(request)
    key = request.POST["key"]
    try:
        member = Member.all_objects.get(upload_registration_form_key=key)
    except Member.DoesNotExist:
        return render_upload_registration_form_invalid(request)

    form = UploadRegistrationForm(request.POST, request.FILES, instance=member)
    if not form.is_valid():
        return render_upload_registration_form(request, member, form, key)
    try:
        form.save()
        member.validate_registration_form()
        return render_upload_registration_form_success(request, member)
    except ValueError:
        return render_upload_registration_form(request, member, form, key)


def confirm_mail(request):
    if request.method == "GET" and "key" in request.GET:
        res = confirm_mail_by_key(request.GET["key"])
        if res:
            return render_mail_confirmation_success(request, res[1], res[0].prename, False)
        else:
            return render_mail_confirmation_invalid(request)
    return HttpResponseRedirect(reverse("startpage:index"))


def render_mail_confirmation_invalid(request):
    return render(request, "members/mail_confirmation_invalid.html")


def render_mail_confirmation_success(request, email, name, parents=False):
    return render(
        request,
        "members/mail_confirmation_success.html",
        {"email": email, "name": name, "parents": parents},
    )


def render_register_waiting_list(request, form=None):
    if form is None:
        form = MemberRegistrationWaitingListForm()
    return render(
        request, "members/register_waiting_list.html", {"form": form, "sektion": settings.SEKTION}
    )


def render_register_waiting_list_success(request, membername):
    return render(request, "members/register_waiting_list_success.html", {"membername": membername})


def register_waiting_list(request):
    if request.method == "GET":
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
    if request.method == "GET" and "key" in request.GET:
        try:
            key = request.GET["key"]
            invitation = InvitationToGroup.objects.get(key=key)
            waiter = invitation.waiter
            if invitation.is_expired() or invitation.rejected:
                raise KeyError
            form = MemberRegistrationForm(instance=waiter)
            return render_register(request, group=invitation.group, form=form, waiter_key=key)
        except InvitationToGroup.DoesNotExist:
            return render_invited_registration_failed(request, _("invalid"))
        except KeyError:
            return render_invited_registration_failed(request, _("expired"))

    # if its a POST request
    return register(request)


def render_invited_registration_failed(request, reason=""):
    context = {}
    if reason:
        context["reason"] = reason
    return render(request, "members/invited_registration_failed.html", context)


def render_reject_invitation(request, invitation):
    return render(
        request,
        "members/reject_invitation.html",
        {"invitation": invitation, "groupname": invitation.group.name},
    )


def render_reject_invalid(request):
    return render(request, "members/reject_invalid.html")


def render_reject_success(request, invitation, leave_waitinglist=False):
    return render(
        request,
        "members/reject_success.html",
        {
            "invitation": invitation,
            "leave_waitinglist": leave_waitinglist,
            "groupname": invitation.group.name,
        },
    )


def reject_invitation(request):
    if request.method == "GET" and "key" in request.GET:
        key = request.GET["key"]
        try:
            invitation = InvitationToGroup.objects.get(key=key)
            if invitation.rejected or invitation.is_expired():
                raise ValueError
            return render_reject_invitation(request, invitation)
        except (ValueError, InvitationToGroup.DoesNotExist):
            return render_reject_invalid(request)
    if request.method != "POST" or "key" not in request.POST:
        return render_reject_invalid(request)
    key = request.POST["key"]
    try:
        invitation = InvitationToGroup.objects.get(key=key)
    except InvitationToGroup.DoesNotExist:
        return render_reject_invalid(request)
    if "reject_invitation" in request.POST:
        invitation.reject()
        return render_reject_success(request, invitation)
    elif "leave_waitinglist" in request.POST:
        invitation.notify_left_waitinglist()
        invitation.waiter.unregister()
        return render_reject_success(request, invitation, leave_waitinglist=True)
    return render_reject_invalid(request)


def render_confirm_invitation(request, invitation):
    return render(
        request,
        "members/confirm_invitation.html",
        {
            "invitation": invitation,
            "groupname": invitation.group.name,
            "contact_email": invitation.group.contact_email,
            "timeinfo": invitation.group.get_time_info(),
        },
    )


def render_confirm_invalid(request):
    return render(request, "members/confirm_invalid.html")


def render_confirm_success(request, invitation):
    return render(
        request,
        "members/confirm_success.html",
        {
            "invitation": invitation,
            "groupname": invitation.group.name,
            "contact_email": invitation.group.contact_email,
            "timeinfo": invitation.group.get_time_info(),
        },
    )


@never_cache
def confirm_invitation(request):
    if request.method == "GET" and "key" in request.GET:
        key = request.GET["key"]
        try:
            invitation = InvitationToGroup.objects.get(key=key)
            if invitation.rejected or invitation.is_expired():
                raise ValueError
            return render_confirm_invitation(request, invitation)
        except (ValueError, InvitationToGroup.DoesNotExist):
            return render_confirm_invalid(request)
    if request.method != "POST" or "key" not in request.POST:
        return render_confirm_invalid(request)
    key = request.POST["key"]
    try:
        invitation = InvitationToGroup.objects.get(key=key)
    except InvitationToGroup.DoesNotExist:
        return render_confirm_invalid(request)
    invitation.confirm()
    return render_confirm_success(request, invitation)


def confirm_waiting(request):
    if request.method == "GET" and "key" in request.GET:
        key = request.GET["key"]
        try:
            waiter = MemberWaitingList.objects.get(wait_confirmation_key=key)
        except MemberWaitingList.DoesNotExist:
            return render_waiting_confirmation_invalid(request)
        status = waiter.confirm_waiting(key)
        if status == MemberWaitingList.WAITING_CONFIRMATION_SUCCESS:
            return render_waiting_confirmation_success(
                request, waiter.prename, already_confirmed=False
            )
        elif status == MemberWaitingList.WAITING_CONFIRMED:
            return render_waiting_confirmation_success(
                request, waiter.prename, already_confirmed=True
            )
        elif status == MemberWaitingList.WAITING_CONFIRMATION_EXPIRED:
            return render_waiting_confirmation_invalid(
                request, prename=waiter.prename, expired=True
            )
        else:
            # invalid
            return render_waiting_confirmation_invalid(request)
    return HttpResponseRedirect(reverse("startpage:index"))


def render_waiting_confirmation_invalid(request, prename=None, expired=False):
    return render(
        request,
        "members/waiting_confirmation_invalid.html",
        {"expired": expired, "prename": prename},
    )


def render_waiting_confirmation_success(request, prename, already_confirmed):
    return render(
        request,
        "members/waiting_confirmation_success.html",
        {"prename": prename, "already_confirmed": already_confirmed},
    )


def render_leave_waitinglist(request, waiter):
    return render(request, "members/leave_waitinglist.html", dict(waiter=waiter))


def render_leave_waitinglist_success(request, waiter):
    return render(request, "members/leave_waitinglist_success.html", dict(waiter=waiter))


def leave_waitinglist(request):
    if request.method == "GET" and "key" in request.GET:
        key = request.GET["key"]
        try:
            waiter = MemberWaitingList.objects.get(leave_key=key)
            return render_leave_waitinglist(request, waiter)
        except (MemberWaitingList.DoesNotExist, MemberWaitingList.MultipleObjectsReturned):
            raise Http404("Waiter with given leave key does not exist.")
    if request.method != "POST" or "key" not in request.POST:
        raise Http404("Waiter with given leave key does not exist.")
    key = request.POST["key"]
    try:
        waiter = MemberWaitingList.objects.get(leave_key=key)
    except (MemberWaitingList.DoesNotExist, MemberWaitingList.MultipleObjectsReturned):
        raise Http404("Waiter with given leave key does not exist.")
    if "leave_waitinglist" not in request.POST:
        raise Http404("leave_waitinglist not found in POST data.")
    waiter.unregister()
    return render_leave_waitinglist_success(request, waiter)
