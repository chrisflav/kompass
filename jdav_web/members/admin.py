import json
from functools import update_wrapper

import nested_admin
from contrib.admin import CommonAdminInlineMixin
from contrib.admin import CommonAdminMixin
from contrib.admin import extra_button
from contrib.admin import ExtraButtonsMixin
from contrib.media import ensure_media_dir
from contrib.media import serve_media
from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib import messages
from django.contrib.admin import DateFieldListFilter
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.contenttypes.admin import GenericTabularInline
from django.core.exceptions import ValidationError
from django.db.models import Case
from django.db.models import ExpressionWrapper
from django.db.models import F
from django.db.models import IntegerField
from django.db.models import Q
from django.db.models import TextField
from django.db.models import When
from django.forms import Textarea
from django.forms import TypedChoiceField
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import path
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from finance.models import BillOnExcursionProxy
from finance.models import StatementOnExcursionProxy
from mailer.models import Message
from schwifty import IBAN
from utils import get_member
from utils import mondays_until_nth
from utils import RestrictedFileField

from .excel import generate_group_overview
from .excel import generate_ljp_vbk
from .models import ActivityCategory
from .models import annotate_activity_score
from .models import EmergencyContact
from .models import Freizeit
from .models import Group
from .models import Intervention
from .models import InvitationToGroup
from .models import Klettertreff
from .models import KlettertreffAttendee
from .models import LJPProposal
from .models import Member
from .models import MemberDocument
from .models import MemberNoteList
from .models import MemberTraining
from .models import MemberUnconfirmedProxy
from .models import MemberWaitingList
from .models import NewMemberOnList
from .models import PermissionGroup
from .models import PermissionMember
from .models import RegistrationPassword
from .models import TrainingCategory
from .models import WEEKDAYS
from .pdf import fill_pdf_form
from .pdf import render_docx
from .pdf import render_tex

# from easy_select2 import apply_select2


class FilteredMemberFieldMixin:
    def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
        """
        Override the queryset for member foreign key fields.
        """
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.related_model != Member:
            return field

        if request is None:
            field.queryset = Member.objects.none()
        elif request.user.has_perm("members.list_global_member"):
            field.queryset = Member.objects.all()
        elif not hasattr(request.user, "member"):
            field.queryset = Member.objects.none()
        else:
            field.queryset = request.user.member.filter_queryset_by_permissions(model=Member)
        return field

    def formfield_for_manytomany(self, db_field, request=None, **kwargs):
        """
        Override the queryset for member many to many fields.
        """
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.related_model != Member:
            return field

        if request is None:
            field.queryset = Member.objects.none()
        elif request.user.has_perm("members.list_global_member"):
            field.queryset = Member.objects.all()
        elif not hasattr(request.user, "member"):
            field.queryset = Member.objects.none()
        else:
            field.queryset = request.user.member.filter_queryset_by_permissions(model=Member)
        return field


class InviteAsUserForm(forms.Form):
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)


class PermissionOnGroupInline(admin.StackedInline):
    model = PermissionGroup
    extra = 1
    can_delete = False


class PermissionOnMemberInline(admin.StackedInline):
    model = PermissionMember
    extra = 1
    can_delete = False


class TrainingOnMemberInline(CommonAdminInlineMixin, admin.TabularInline):
    model = MemberTraining
    description = _(
        "Please enter all training courses and further education courses that you have already attended or will be attending soon. Please also upload your confirmation of participation so that the responsible person can fill in the 'Attended' and 'Passed' fields. If the activity selection does not match your training, please describe it in the comment field."
    )
    formfield_overrides = {TextField: {"widget": Textarea(attrs={"rows": 1, "cols": 25})}}
    ordering = ("date",)
    extra = 1

    field_change_permissions = {
        "participated": "members.manage_success_trainings",
        "passed": "members.manage_success_trainings",
    }


class EmergencyContactInline(CommonAdminInlineMixin, admin.TabularInline):
    model = EmergencyContact
    description = _(
        "Please enter at least one emergency contact with contact details here. These are necessary for crisis intervention during trips."
    )
    formfield_overrides = {TextField: {"widget": Textarea(attrs={"rows": 1, "cols": 40})}}
    fields = ["prename", "lastname", "email", "phone_number"]
    extra = 0


class MemberDocumentInline(CommonAdminInlineMixin, admin.TabularInline):
    model = MemberDocument
    description = _(
        "Upload additional documents (e.g., medical forms, parental consent for medication). "
        "These documents are stored centrally and accessible during emergencies."
    )
    formfield_overrides = {
        RestrictedFileField: {
            "widget": forms.ClearableFileInput(
                attrs={"accept": "application/pdf,image/jpeg,image/png"}
            )
        },
    }
    fields = ["f"]
    extra = 0


class TrainingCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "permission_needed")
    ordering = ("name",)


class CreateObjectFromForm(forms.Form):
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)


class CrisisInterventionListForm(forms.Form):
    """Form for creating a crisis intervention list for ad-hoc activities."""

    activity = forms.CharField(
        max_length=50,
        label=_("Activity"),
        help_text=_("Name of the activity"),
    )
    place = forms.CharField(
        max_length=50,
        label=_("Location"),
        help_text=_("Location where the activity takes place"),
    )
    start_date = forms.DateField(
        label=_("Start date"),
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        help_text=_("Start date of the activity"),
        initial=timezone.now().strftime("%Y-%m-%d"),
    )
    end_date = forms.DateField(
        label=_("End date"),
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        help_text=_("End date of the activity"),
        initial=timezone.now().strftime("%Y-%m-%d"),
    )
    description = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4}),
        label=_("Description"),
        help_text=_("Description of the activity"),
        required=False,
    )
    youth_leaders = forms.ModelMultipleChoiceField(
        queryset=Member.objects.all(),
        label=_("Youth leaders"),
        help_text=_("Youth leaders supervising the activity"),
        required=False,
        widget=FilteredSelectMultiple(_("Youth leaders"), is_stacked=False),
    )
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        label=_("Groups"),
        help_text=_("Groups participating in the activity"),
        required=False,
        widget=FilteredSelectMultiple(_("Groups"), is_stacked=False),
    )


def generate_crisis_intervention_list_pdf(
    *,
    name,
    description,
    code,
    place,
    destination,
    groups,
    staff,
    start_date,
    end_date,
    tour_type,
    tour_approach,
    members,
):
    """Generate a crisis intervention list PDF.

    Args:
        name: Activity name
        description: Activity description
        code: Activity code (e.g., K-260101)
        place: Location of the activity
        destination: Destination (optional, e.g., a peak)
        groups: List or queryset of Group objects
        staff: List or queryset of Member objects (youth leaders)
        start_date: Start date of the activity
        end_date: End date of the activity
        tour_type: Tour type identifier (empty string for ad-hoc lists)
        tour_approach: Tour approach identifier (empty string for ad-hoc lists)
        members: List of Member objects participating in the activity

    Returns:
        HttpResponse with the generated PDF
    """
    # Format groups string
    groups_str = ", ".join([g.name for g in groups]) if groups else ""

    # Format staff string
    staff_str = ", ".join([s.name for s in staff]) if staff else ""

    # Format time period string
    # Handle both date and datetime objects
    start_date_only = start_date.date() if hasattr(start_date, "date") else start_date
    end_date_only = end_date.date() if hasattr(end_date, "date") else end_date

    if start_date_only == end_date_only:
        time_period_str = start_date_only.strftime("%d.%m.%Y")
    else:
        time_period_str = (
            f"{start_date_only.strftime('%d.%m.%Y')} - {end_date_only.strftime('%d.%m.%Y')}"
        )

    context = {
        "name": name,
        "description": description,
        "code": code,
        "place": place,
        "destination": destination,
        "groups_str": groups_str,
        "staff_str": staff_str,
        "time_period_str": time_period_str,
        "tour_type": tour_type,
        "tour_approach": tour_approach,
        "members": members,
        "settings": settings,
    }

    # Use description for filename if name is long, otherwise use name
    filename_base = description if len(name) > 30 else name
    return render_tex(
        f"{filename_base}_Krisenliste",
        "members/crisis_intervention_list.tex",
        context,
        date=start_date,
    )


class MemberAdminForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = "__all__"

    # check iban validity using schwifty package
    def clean_iban(self):
        iban_str = self.cleaned_data.get("iban")
        if len(iban_str) > 0:
            iban = IBAN(iban_str, allow_invalid=True)
            if not iban.is_valid:
                raise ValidationError(_("The entered IBAN is not valid."))
        return iban_str


# Register your models here.
class MemberAdmin(ExtraButtonsMixin, CommonAdminMixin, admin.ModelAdmin):
    fieldsets = [
        (
            None,
            {
                "fields": [
                    ("prename", "lastname"),
                    ("email", "alternative_email"),
                    "phone_number",
                    "birth_date",
                    "gender",
                    "group",
                    "registration_form",
                    "image",
                    ("join_date", "leave_date"),
                    "comments",
                    "legal_guardians",
                    "active",
                    "echoed",
                    "user",
                ]
            },
        ),
        (
            _("Contact information"),
            {"fields": ["street", "plz", "town", "address_extra", "country", "iban"]},
        ),
        (
            _("Skills"),
            {
                "classes": ["show-excursions-link"],
                "fields": [
                    "swimming_badge",
                    "climbing_badge",
                    "alpine_experience",
                    "show_excursions_link",
                ],
            },
        ),
        (
            _("Others"),
            {
                "fields": [
                    "dav_badge_no",
                    "ticket_no",
                    "allergies",
                    "tetanus_vaccination",
                    "medication",
                    "photos_may_be_taken",
                    "may_cancel_appointment_independently",
                ]
            },
        ),
        (
            _("Organizational"),
            {
                "fields": [
                    ("good_conduct_certificate_presented_date", "good_conduct_certificate_valid"),
                    "has_key",
                    "has_free_ticket_gym",
                ]
            },
        ),
    ]
    list_display = (
        "name_text_or_link",
        "birth_date",
        "age",
        "get_group",
        "email_mailto_link",
        "phone_number_tel_link",
        "echoed",
        "comments",
        "activity_score",
    )
    search_fields = ("prename", "lastname", "email")
    list_filter = ("echoed", "group")
    list_display_links = None
    readonly_fields = ["echoed", "good_conduct_certificate_valid", "show_excursions_link"]
    inlines = [
        EmergencyContactInline,
        MemberDocumentInline,
        TrainingOnMemberInline,
        PermissionOnMemberInline,
    ]
    formfield_overrides = {
        RestrictedFileField: {
            "widget": forms.ClearableFileInput(
                attrs={"accept": "application/pdf,image/jpeg,image/png"}
            )
        },
    }
    change_form_template = "members/change_member.html"
    ordering = ("lastname",)
    actions = ["create_object_from", "request_echo", "invite_as_user_action", "unconfirm"]
    list_per_page = 25

    form = MemberAdminForm

    sensitive_fields = ["iban", "registration_form", "comments"]

    field_view_permissions = {
        "user": "members.may_set_auth_user",
        "good_conduct_certificate_presented_date": "members.may_change_organizationals",
        "has_key": "members.may_change_organizationals",
        "has_free_ticket_gym": "members.may_change_organizationals",
    }

    field_change_permissions = {
        "user": "members.may_set_auth_user",
        "group": "members.may_change_member_group",
        "good_conduct_certificate_presented_date": "members.may_change_organizationals",
        "has_key": "members.may_change_organizationals",
        "has_free_ticket_gym": "members.may_change_organizationals",
    }

    def get_urls(self):
        urls = super().get_urls()

        def wrap(view):
            def wrapper(*args, **kwargs):
                return self.admin_site.admin_view(view)(*args, **kwargs)

            wrapper.model_admin = self
            return update_wrapper(wrapper, view)

        custom_urls = [
            path(
                "create_crisis_intervention_list/",
                wrap(self.create_crisis_intervention_list_view),
                name="{}_{}_create_crisis_intervention_list".format(
                    self.opts.app_label, self.opts.model_name
                ),
            ),
        ]
        return custom_urls + urls

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return annotate_activity_score(queryset.prefetch_related("group"))

    def change_view(self, request, object_id, form_url="", extra_context=None):
        try:
            extra_context = extra_context or {}
            extra_context["qualities"] = Member.objects.get(pk=object_id).get_skills()
            extra_context["activities"] = Member.objects.get(pk=object_id).get_activities()
            return super().change_view(
                request, object_id, form_url=form_url, extra_context=extra_context
            )
        except Member.DoesNotExist:
            return super().change_view(request, object_id)

    def send_mail_to(self, request, queryset):
        member_pks = [m.pk for m in queryset]
        query = str(member_pks).replace(" ", "")
        return HttpResponseRedirect(
            reverse("admin:mailer_message_add") + "?members={}".format(query)
        )

    send_mail_to.short_description = _("Compose new mail to selected members")

    def show_excursions_link(self, obj):
        url = reverse("admin:members_freizeit_changelist") + f"?has_participant={obj.pk}"
        text = _("Link to excursions")
        return format_html(f"<a href='{url}'>{text}</a>")

    show_excursions_link.short_description = _("Participated in excursions")

    def create_object_from(self, request, queryset):
        """
        Create an object from the selected members. This can be one of
        - `MemberNoteList`
        - `Freizeit`
        - `Message`
        - `CrisisInterventionList` (generates PDF directly)
        """
        MODELS = {
            "MemberNoteList": MemberNoteList,
            "Excursion": Freizeit,
            "Message": Message,
        }
        choice = request.POST.get("choice")

        # Handle crisis intervention list separately (no model, direct to form)
        if "create" in request.POST and choice == "CrisisInterventionList":
            member_pks = [m.pk for m in queryset]
            query = str(member_pks).replace(" ", "")
            return HttpResponseRedirect(
                reverse("admin:members_member_create_crisis_intervention_list")
                + "?members={}".format(query)
            )

        model = MODELS.get(choice)
        if "create" in request.POST and model is not None:
            member_pks = [m.pk for m in queryset]
            query = str(member_pks).replace(" ", "")

            return HttpResponseRedirect(
                reverse("admin:{}_{}_add".format(model._meta.app_label, model._meta.model_name))
                + "?members={}".format(query)
            )

        elif "add_to_selected" in request.POST:
            choice = request.POST.get("choice")
            entry_id = request.POST.get("existing_entry")
            model = MODELS.get(choice)
            if entry_id is None or model is None:
                # If validation failed, return to member list
                return HttpResponseRedirect(
                    reverse(
                        "admin:{}_{}_changelist".format(self.opts.app_label, self.opts.model_name)
                    )
                )

            try:
                obj = model.objects.get(pk=entry_id)
                obj.add_members(queryset)
                messages.success(
                    request,
                    _("Successfully added %(count)s member(s) to %(model)s '%(obj)s'.")
                    % {
                        "count": queryset.count(),
                        "model": model._meta.verbose_name,
                        "obj": str(obj),
                    },
                )
                return HttpResponseRedirect(
                    reverse(
                        "admin:{}_{}_change".format(model._meta.app_label, model._meta.model_name),
                        args=(entry_id,),
                    )
                )
            except model.DoesNotExist:
                messages.error(
                    request,
                    _("Selected %(model)s does not exist.") % {"model": model._meta.verbose_name},
                )

        # Check permissions and prepare allowed choices
        allowed_choices = []
        existing_entries = {}

        # Configuration for ordering (only thing that varies by model)
        MODEL_ORDERING = {
            "MemberNoteList": "-date",
            "Excursion": "-date",
            "Message": "-pk",
        }

        # Iterate through MODELS and set allowed_choices and existing_entries
        for key, model_class in MODELS.items():
            permission = f"{model_class._meta.app_label}.add_global_{model_class._meta.model_name}"
            if request.user.has_perm(permission):
                allowed_choices.append(
                    {"value": key, "label": model_class._meta.verbose_name.title()}
                )
                existing_entries[key] = [
                    {"id": obj.pk, "display": obj.get_dropdown_display()}
                    for obj in model_class.filter_queryset_by_change_permissions(
                        request.user
                    ).order_by(MODEL_ORDERING[key])
                ]

        # Add Crisis Intervention List option (create only, no add to existing)
        if request.user.has_perm("members.add_global_freizeit"):
            allowed_choices.append(
                {"value": "CrisisInterventionList", "label": _("Crisis Intervention List")}
            )

        id_list = queryset.values_list("id", flat=True)
        context = dict(
            self.admin_site.each_context(request),
            title=_("Create object from selected members"),
            opts=self.opts,
            queryset=queryset,
            # Ensures that follow-up requests are still handled by this view
            form=CreateObjectFromForm(initial={"_selected_action": id_list}),
            allowed_choices=allowed_choices,
            existing_entries_json=json.dumps(existing_entries),
        )
        return render(request, "admin/create_object_from.html", context=context)

    create_object_from.short_description = _("Create object from selected members.")

    def request_echo(self, request, queryset):
        # make sure to show the successful banner only if any successful
        # emails were actually scheduled. If only one person is about to get echoed
        # but hasn't set a birthdate, don't show success
        success = False

        for member in queryset:
            if not member.gets_newsletter:
                continue
            if not member.birth_date:
                messages.error(
                    request,
                    _(
                        "Member {name} doesn't have a birthdate set, which is mandatory for echo requests"
                    ).format(name=member.name),
                )
            else:
                member.request_echo()
                success = True
        if success:
            messages.success(request, _("Successfully requested echo from selected members."))

    request_echo.short_description = _("Request echo from selected members")

    @extra_button(_("Request echo"), url_name="requestecho")
    def request_echo_view(self, request, member):
        """Request echo from a single member from Button in single member view."""
        if not member.gets_newsletter:
            messages.warning(
                request, _("%(name)s does not receive the newsletter.") % {"name": member.name}
            )
        elif not member.birth_date:
            messages.error(
                request,
                _(
                    "Member {name} doesn't have a birthdate set, which is mandatory for echo requests"
                ).format(name=member.name),
            )
        else:
            member.request_echo()
            messages.success(
                request, _("Successfully requested echo from %(name)s.") % {"name": member.name}
            )

        return HttpResponseRedirect(
            reverse(
                "admin:{}_{}_change".format(self.opts.app_label, self.opts.model_name),
                args=(member.pk,),
            )
        )

    def invite_as_user(self, request, queryset):
        failures = []
        for member in queryset:
            success = member.invite_as_user()
            if not success:
                failures.append(member)
                messages.error(
                    request,
                    _("%(name)s does not have a DAV360 email address or is already registered.")
                    % {"name": member.name},
                )
        if queryset.count() == 1 and len(failures) == 0:
            messages.success(
                request, _("Successfully invited %(name)s as user.") % {"name": queryset[0].name}
            )
        elif len(failures) == 0:
            messages.success(request, _("Successfully invited selected members to join as users."))
        else:
            messages.warning(
                request, _("Some members have been invited, others could not be invited.")
            )

    def request_password_reset(self, request, member):
        success = member.request_password_reset()
        if success:
            messages.success(
                request, _("Password reset email sent to %(name)s.") % {"name": str(member)}
            )
        else:
            messages.error(request, _("Could not send password reset email."))

    def has_may_invite_as_user_permission(self, request):
        return request.user.has_perm("{}.{}".format(self.opts.app_label, "may_invite_as_user"))

    def invite_as_user_action(self, request, queryset):
        if not request.user.has_perm("members.may_invite_as_user"):  # pragma: no cover
            # this should be unreachable, because of allowed_permissions attribute
            messages.error(request, _("Permission denied."))
            return HttpResponseRedirect(
                reverse("admin:{}_{}_changelist".format(self.opts.app_label, self.opts.model_name))
            )
        if "apply" in request.POST:
            self.invite_as_user(request, queryset)
            return HttpResponseRedirect(
                reverse("admin:{}_{}_changelist".format(self.opts.app_label, self.opts.model_name))
            )

        context = dict(
            self.admin_site.each_context(request),
            title=_("Invite as user"),
            view_header=_("Invite multiple members as users"),
            opts=self.opts,
            members=queryset,
            form=InviteAsUserForm(
                initial={"_selected_action": queryset.values_list("id", flat=True)}
            ),
        )
        return render(request, "admin/invite_selected_as_user.html", context=context)

    invite_as_user_action.short_description = _("Invite selected members to join Kompass as users.")
    invite_as_user_action.allowed_permissions = ("may_invite_as_user",)

    @extra_button(
        _("Invite as user"),
        url_name="inviteasuser",
        permission="members.may_invite_as_user",
        dynamic_label=lambda m: _("Request password reset") if m.user else _("Invite as user"),
    )
    def invite_as_user_view(self, request, member):
        is_password_reset = bool(member.user)
        if not member.has_internal_email():
            messages.error(
                request,
                _("The configured email address for %(name)s is not an internal one.")
                % {"name": str(member)},
            )
            return HttpResponseRedirect(
                reverse(
                    "admin:{}_{}_change".format(self.opts.app_label, self.opts.model_name),
                    args=(member.pk,),
                )
            )
        if "apply" in request.POST:
            if is_password_reset:
                self.request_password_reset(request, member)
            else:
                self.invite_as_user(request, Member.objects.filter(pk=member.pk))
            return HttpResponseRedirect(
                reverse(
                    "admin:{}_{}_change".format(self.opts.app_label, self.opts.model_name),
                    args=(member.pk,),
                )
            )

        context = dict(
            self.admin_site.each_context(request),
            title=_("Reset password") if is_password_reset else _("Invite as user"),
            opts=self.opts,
            member=member,
            object=member,
            is_password_reset=is_password_reset,
        )
        if member.invite_as_user_key:
            if is_password_reset:
                messages.warning(
                    request,
                    _("{name} already has a pending password reset link.").format(name=str(member)),
                )
            else:
                messages.warning(
                    request,
                    _("{name} already has a pending invitation as user.").format(name=str(member)),
                )
        return render(request, "admin/invite_as_user.html", context=context)

    def activity_score(self, obj):
        score = obj._activity_score
        # show 1 to 5 climbers based on activity in last year
        if score < 5:
            level = 1
        elif score >= 5 and score < 10:
            level = 2
        elif score >= 10 and score < 20:
            level = 3
        elif score >= 20 and score < 30:
            level = 4
        else:
            level = 5
        return format_html(
            level * '<img height=20px src="{}"/>&nbsp;'.format("/static/admin/img/climber.png")
        )

    activity_score.admin_order_field = "_activity_score"
    activity_score.short_description = _("activity")

    def name_text_or_link(self, obj):
        if not hasattr(obj, "_viewable") or obj._viewable:
            return format_html(
                '<a href="{link}">{name}</a>'.format(
                    link=reverse(
                        "admin:{}_{}_change".format(self.opts.app_label, self.opts.model_name),
                        args=(obj.pk,),
                    ),
                    name=obj.name,
                )
            )
        else:
            return obj.name

    name_text_or_link.short_description = _("Name")
    name_text_or_link.admin_order_field = "lastname"

    def unconfirm(self, request, queryset):
        for member in queryset:
            member.unconfirm()
        messages.success(request, _("Successfully unconfirmed selected members."))

    unconfirm.short_description = _("Unconfirm selected members.")

    def create_crisis_intervention_list_view(self, request):
        """View for creating crisis intervention lists for ad-hoc activities."""
        # Get selected members from query parameter
        raw_members = request.GET.get("members", "")
        try:
            m_ids = json.loads(raw_members)
            if not isinstance(m_ids, list):
                raise ValueError()
            members = Member.objects.filter(pk__in=m_ids)
            if not members.exists():
                raise ValueError()
        except (json.JSONDecodeError, ValueError):
            messages.error(request, _("Invalid member selection."))
            return HttpResponseRedirect(
                reverse("admin:{}_{}_changelist".format(self.opts.app_label, self.opts.model_name))
            )

        # Handle form submission
        if request.method == "POST":
            form = CrisisInterventionListForm(request.POST)
            if form.is_valid():
                form_data = form.cleaned_data

                # Generate PDF using shared function
                return generate_crisis_intervention_list_pdf(
                    name=form_data["activity"],
                    description=form_data["description"],
                    code=f"K-{timezone.now():%y%m%d}",
                    place=form_data["place"],
                    destination="",
                    groups=form_data.get("groups", []),
                    staff=form_data.get("youth_leaders", []),
                    start_date=form_data["start_date"],
                    end_date=form_data["end_date"],
                    tour_type="",
                    tour_approach="",
                    members=list(members),
                )
        else:
            form = CrisisInterventionListForm()

        # Render form template
        context = dict(
            self.admin_site.each_context(request),
            title=_("Create Crisis Intervention List"),
            opts=self.opts,
            form=form,
            members=members,
            members_json=raw_members,
        )
        return render(request, "admin/create_crisis_intervention_list.html", context=context)


class DemoteToWaiterForm(forms.Form):
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)


class MemberUnconfirmedAdmin(ExtraButtonsMixin, CommonAdminMixin, admin.ModelAdmin):
    extra_buttons_model = MemberUnconfirmedProxy
    fieldsets = [
        (
            None,
            {
                "fields": [
                    ("prename", "lastname"),
                    ("email", "alternative_email"),
                    "phone_number",
                    "birth_date",
                    "gender",
                    "group",
                    "registration_form",
                    "image",
                    ("join_date", "leave_date"),
                    "comments",
                    "legal_guardians",
                    "dav_badge_no",
                    "echoed",
                    "user",
                ]
            },
        ),
        (
            _("Contact information"),
            {"fields": ["street", "plz", "town", "address_extra", "country", "iban"]},
        ),
        (_("Skills"), {"fields": ["swimming_badge", "climbing_badge", "alpine_experience"]}),
        (
            _("Others"),
            {"fields": ["allergies", "tetanus_vaccination", "medication", "photos_may_be_taken"]},
        ),
        (
            _("Organizational"),
            {
                "fields": [
                    ("good_conduct_certificate_presented_date", "good_conduct_certificate_valid"),
                    "has_key",
                    "has_free_ticket_gym",
                ]
            },
        ),
    ]
    list_display = (
        "name",
        "birth_date",
        "age",
        "get_group",
        "confirmed_mail",
        "confirmed_alternative_mail",
        "registration_form_uploaded",
    )
    search_fields = ("prename", "lastname", "email")
    list_filter = ("group", "confirmed_mail", "confirmed_alternative_mail")
    readonly_fields = [
        "confirmed_mail",
        "confirmed_alternative_mail",
        "good_conduct_certificate_valid",
        "echoed",
    ]
    actions = [
        "request_mail_confirmation",
        "request_required_mail_confirmation",
        "confirm",
        "demote_to_waiter_action",
    ]
    inlines = [EmergencyContactInline]
    change_form_template = "members/change_member_unconfirmed.html"

    field_view_permissions = {
        "user": "members.may_set_auth_user",
        "good_conduct_certificate_presented_date": "members.may_change_organizationals",
        "has_key": "members.may_change_organizationals",
        "has_free_ticket_gym": "members.may_change_organizationals",
    }

    field_change_permissions = {
        "user": "members.may_set_auth_user",
        "group": "members.may_change_member_group",
        "good_conduct_certificate_presented_date": "members.may_change_organizationals",
        "has_key": "members.may_change_organizationals",
        "has_free_ticket_gym": "members.may_change_organizationals",
    }

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.has_perm("members.may_manage_all_registrations"):
            return queryset
        if not hasattr(request.user, "member"):
            return MemberUnconfirmedProxy.objects.none()
        groups = request.user.member.leited_groups.all()
        # this is magic (the first part, group is a manytomanyfield) but seems to work
        return queryset.filter(group__in=groups).distinct()

    def request_mail_confirmation(self, request, queryset):
        for member in queryset:
            member.request_mail_confirmation()
        messages.success(
            request, _("Successfully requested mail confirmation from selected registrations.")
        )

    request_mail_confirmation.short_description = _(
        "Request mail confirmation from selected registrations"
    )

    def request_required_mail_confirmation(self, request, queryset):
        for member in queryset:
            member.request_mail_confirmation(rerequest=False)
        messages.success(
            request,
            _("Successfully re-requested missing mail confirmations from selected registrations."),
        )

    request_required_mail_confirmation.short_description = _(
        "Re-request missing mail confirmations from selected registrations."
    )

    def confirm(self, request, queryset):
        notify_individual = len(queryset.all()) < 10
        success = True
        for member in queryset:
            confirmed = member.confirm()
            if not confirmed:
                success = False
            if notify_individual:
                if confirmed:
                    messages.success(
                        request, _("Successfully confirmed %(name)s.") % {"name": member.name}
                    )
                else:
                    messages.error(
                        request,
                        _("Can't confirm. %(name)s has unconfirmed email addresses.")
                        % {"name": member.name},
                    )
        if notify_individual:
            return
        if success:
            messages.success(request, _("Successfully confirmed multiple registrations."))
        else:
            messages.error(
                request,
                _("Failed to confirm some registrations because of unconfirmed email addresses."),
            )

    confirm.short_description = _("Confirm selected registrations")

    def demote_to_waiter_action(self, request, queryset):
        return self.demote_to_waiter_view(request, queryset)

    demote_to_waiter_action.short_description = _("Demote selected registrations to waiters.")

    @extra_button(_("Demote to waiter"), url_name="demote")
    def demote_to_waiter_view(self, request, member_or_queryset):
        if isinstance(member_or_queryset, MemberUnconfirmedProxy):
            queryset = [member_or_queryset]
            form = None
        else:
            queryset = member_or_queryset
            form = DemoteToWaiterForm(
                initial={"_selected_action": queryset.values_list("id", flat=True)}
            )

        if "apply" in request.POST:
            self.demote_to_waiter(request, queryset)
            return HttpResponseRedirect(reverse("admin:members_memberunconfirmedproxy_changelist"))

        context = dict(
            self.admin_site.each_context(request),
            title=_("Demote member to waiter"),
            view_header=_("Demote to waiter"),
            opts=self.opts,
            queryset=queryset,
            form=form,
        )
        return render(request, "admin/demote_to_waiter.html", context=context)

    def demote_to_waiter(self, request, queryset):
        for member in queryset:
            member.demote_to_waiter()
            messages.success(
                request, _("Successfully demoted %(name)s to waiter.") % {"name": member.name}
            )

    @extra_button(_("Request registration form"))
    def request_registration_form_view(self, request, member):
        if "apply" in request.POST:
            member.request_registration_form()
            messages.success(
                request, _("Requested registration form for %(name)s.") % {"name": member.name}
            )
            return HttpResponseRedirect(
                reverse("admin:members_memberunconfirmedproxy_change", args=(member.pk,))
            )
        context = dict(
            self.admin_site.each_context(request),
            title=_("Request upload registration form"),
            view_header=_("Request registration form"),
            opts=self.opts,
            member=member,
            object=member,
        )
        return render(request, "admin/request_registration_form.html", context=context)

    def response_change(self, request, member):
        if "_confirm" in request.POST:
            if member.confirm():
                messages.success(
                    request, _("Successfully confirmed %(name)s.") % {"name": member.name}
                )
            else:
                messages.error(
                    request,
                    _("Can't confirm. %(name)s has unconfirmed email addresses.")
                    % {"name": member.name},
                )
        return super().response_change(request, member)


class WaiterInviteForm(forms.Form):
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)
    group = forms.ModelChoiceField(queryset=Group.objects.all(), label=_("Group"))


class WaiterInviteTextForm(forms.Form):
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)
    text_template = forms.CharField(
        label=_("Invitation text"), widget=forms.Textarea(attrs={"rows": 30, "cols": 100})
    )


class InvitationToGroupAdmin(CommonAdminInlineMixin, admin.TabularInline):
    model = InvitationToGroup
    fields = ["group", "date", "status"]
    readonly_fields = ["group", "date", "status"]
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class AgeFilter(admin.SimpleListFilter):
    title = _("Age")
    parameter_name = "age"

    def lookups(self, request, model_admin):
        return [(n, str(n)) for n in range(101)]

    def queryset(self, request, queryset):
        age = self.value()
        if not age:
            return queryset
        return queryset.filter(birth_date_delta=age)


class InvitedToGroupFilter(admin.SimpleListFilter):
    title = _("Pending group invitation for group")
    parameter_name = "pending_group_invitation"

    def lookups(self, request, model_admin):
        return [(g.pk, g.name) for g in Group.objects.all()]

    def queryset(self, request, queryset):
        pk = self.value()
        if not pk:
            return queryset
        return queryset.filter(
            invitationtogroup__group__pk=pk,
            invitationtogroup__rejected=False,
            invitationtogroup__date__gt=(timezone.now() - timezone.timedelta(days=30)).date(),
        ).distinct()


class MemberWaitingListAdmin(ExtraButtonsMixin, CommonAdminMixin, admin.ModelAdmin):
    fields = [
        "prename",
        "lastname",
        "email",
        "birth_date",
        "gender",
        "application_text",
        "application_date",
        "comments",
        "sent_reminders",
    ]
    list_display = (
        "name",
        "birth_date",
        "age",
        "gender",
        "application_date",
        "latest_group_invitation",
        "confirmed_mail",
        "waiting_confirmed",
        "sent_reminders",
    )
    search_fields = ("prename", "lastname", "email")
    list_filter = ["confirmed_mail", InvitedToGroupFilter, AgeFilter, "gender"]
    actions = [
        "ask_for_registration_action",
        "ask_for_wait_confirmation",
        "request_mail_confirmation",
        "request_required_mail_confirmation",
    ]
    inlines = [InvitationToGroupAdmin]
    readonly_fields = ["application_date", "sent_reminders"]

    def has_add_permission(self, request, obj=None):
        return False

    def has_action_permission(self, request):
        return request.user.has_perm("members.change_global_memberwaitinglist")

    def age(self, obj):
        return obj.birth_date_delta

    age.short_description = _("age")
    age.admin_order_field = "birth_date_delta"

    def ask_for_wait_confirmation(self, request, queryset):
        """Asks the waiting person to confirm their waiting status."""
        for waiter in queryset:
            waiter.ask_for_wait_confirmation()
            messages.success(
                request,
                _("Successfully asked %(name)s to confirm their waiting status.")
                % {"name": waiter.name},
            )

    ask_for_wait_confirmation.short_description = _(
        "Ask selected waiters to confirm their waiting status"
    )
    ask_for_wait_confirmation.allowed_permissions = ("action",)

    def response_change(self, request, waiter):
        ret = super().response_change(request, waiter)
        if "_invite" in request.POST:
            return HttpResponseRedirect(
                reverse(
                    "admin:{}_{}_invite".format(waiter._meta.app_label, waiter._meta.model_name),
                    args=(waiter.pk,),
                )
            )
        return ret

    def request_mail_confirmation(self, request, queryset):
        for member in queryset:
            member.request_mail_confirmation()
        messages.success(
            request, _("Successfully requested mail confirmation from selected waiters.")
        )

    request_mail_confirmation.short_description = _(
        "Request mail confirmation from selected waiters."
    )
    request_mail_confirmation.allowed_permissions = ("action",)

    def request_required_mail_confirmation(self, request, queryset):
        for member in queryset:
            member.request_mail_confirmation(rerequest=False)
        messages.success(
            request,
            _("Successfully re-requested missing mail confirmations from selected waiters."),
        )

    request_required_mail_confirmation.short_description = _(
        "Re-request missing mail confirmations from selected waiters."
    )
    request_required_mail_confirmation.allowed_permissions = ("action",)

    def get_queryset(self, request):
        now = timezone.now()
        age_expr = ExpressionWrapper(
            Case(
                # if the month of the birth date has not yet passed, subtract one year
                When(birth_date__month__gt=now.month, then=now.year - F("birth_date__year") - 1),
                # if it is the month of the birth date but the day has not yet passed, subtract one year
                When(
                    birth_date__month=now.month,
                    birth_date__day__gt=now.day,
                    then=now.year - F("birth_date__year") - 1,
                ),
                # otherwise return the difference in years
                default=now.year - F("birth_date__year"),
            ),
            output_field=IntegerField(),
        )
        queryset = super().get_queryset(request).annotate(birth_date_delta=age_expr)
        return queryset.prefetch_related("invitationtogroup_set")

    def ask_for_registration_action(self, request, queryset):
        return self.invite_view(request, queryset)

    ask_for_registration_action.short_description = _("Offer waiter a place in a group.")
    ask_for_registration_action.allowed_permissions = ("action",)

    @extra_button(_("Invite to group"), permission="members.change_global_memberwaitinglist")
    def invite_view(self, request, waiter_or_queryset):
        if isinstance(waiter_or_queryset, MemberWaitingList):
            waiter = waiter_or_queryset
            queryset = [waiter]
            id_list = [waiter.pk]
        else:
            waiter = None
            queryset = waiter_or_queryset
            id_list = queryset.values_list("id", flat=True)

        if "apply" in request.POST:
            try:
                group = Group.objects.get(pk=request.POST["group"])
            except Group.DoesNotExist:
                messages.error(
                    request,
                    _("An error occurred while trying to invite said members. Please try again."),
                )
                return HttpResponseRedirect(request.get_full_path())

            if not group.contact_email:
                messages.error(
                    request,
                    _(
                        "The selected group does not have a contact email. Please first set a contact email and then try again."
                    ),
                )
                return HttpResponseRedirect(request.get_full_path())
            context = dict(
                self.admin_site.each_context(request),
                title=_("Select group for invitation"),
                view_header=_("Invite to group"),
                opts=self.opts,
                group=group,
                queryset=queryset,
                form=WaiterInviteTextForm(
                    initial={
                        "_selected_action": id_list,
                        "text_template": group.get_invitation_text_template(),
                    }
                ),
            )
            if waiter:
                context = dict(context, object=waiter, waiter=waiter)
            return render(request, "admin/invite_for_group_text.html", context=context)

        if "send" in request.POST:
            try:
                group = Group.objects.get(pk=request.POST["group"])
                text_template = request.POST["text_template"]
            except (Group.DoesNotExist, KeyError):
                messages.error(
                    request,
                    _("An error occurred while trying to invite said members. Please try again."),
                )
                return HttpResponseRedirect(request.get_full_path())
            for w in queryset:
                w.invite_to_group(
                    group,
                    text_template=text_template,
                    creator=request.user.member if hasattr(request.user, "member") else None,
                )
                messages.success(
                    request,
                    _("Successfully invited %(name)s to %(group)s.")
                    % {"name": w.name, "group": w.invited_for_group.name},
                )

            if waiter:
                return HttpResponseRedirect(
                    reverse(
                        "admin:{}_{}_change".format(self.opts.app_label, self.opts.model_name),
                        args=(waiter.pk,),
                    )
                )
            else:
                return HttpResponseRedirect(
                    reverse(
                        "admin:{}_{}_changelist".format(self.opts.app_label, self.opts.model_name)
                    )
                )

        context = dict(
            self.admin_site.each_context(request),
            title=_("Select group for invitation"),
            view_header=_("Invite to group"),
            opts=self.opts,
            queryset=queryset,
            form=WaiterInviteForm(initial={"_selected_action": id_list}),
        )
        if waiter:
            context = dict(context, object=waiter, waiter=waiter)
        return render(request, "admin/invite_for_group.html", context=context)


class RegistrationPasswordInline(admin.TabularInline):
    model = RegistrationPassword
    extra = 0


class GroupAdminForm(forms.ModelForm):
    name = forms.RegexField(
        regex=r"^{pattern}+$".format(pattern=settings.STARTPAGE_URL_NAME_PATTERN),
        label=_("name"),
        error_messages={
            "invalid": _(
                "The group name may only consist of letters, numerals, _, -, :, * and spaces."
            )
        },
    )

    class Meta:
        model = Freizeit
        exclude = ["add_member"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "leiters" in self.fields:
            self.fields["leiters"].queryset = Member.objects.filter(group__name="Jugendleiter")


class GroupAdmin(admin.ModelAdmin):
    fields = [
        "name",
        "description",
        "year_from",
        "year_to",
        "leiters",
        "contact_email",
        "show_website",
        "weekday",
        ("start_time", "end_time"),
    ]
    form = GroupAdminForm
    list_display = ("name", "year_from", "year_to")
    inlines = [RegistrationPasswordInline, PermissionOnGroupInline]
    search_fields = ("name",)

    def get_urls(self):
        urls = super().get_urls()

        def wrap(view):
            def wrapper(*args, **kwargs):
                return self.admin_site.admin_view(view)(*args, **kwargs)

            wrapper.model_admin = self
            return update_wrapper(wrapper, view)

        custom_urls = [
            path("action/", wrap(self.action_view), name="members_group_action"),
        ]
        return custom_urls + urls

    def action_view(self, request):
        if "group_overview" in request.POST:
            return self.group_overview(request)
        elif "group_checklist" in request.POST:
            return self.group_checklist(request)

    def group_overview(self, request):
        if not request.user.has_perm("members.view_group"):
            messages.error(request, _("You are not allowed to create a group overview."))
            return HttpResponseRedirect(
                reverse("admin:{}_{}_changelist".format(self.opts.app_label, self.opts.model_name))
            )

        ensure_media_dir()
        filename = generate_group_overview(all_groups=self.model.objects.all())
        response = serve_media(filename=filename, content_type="application/xlsx")

        return response

    def group_checklist(self, request):
        if not request.user.has_perm("members.view_group"):
            messages.error(request, _("You are not allowed to create a group checklist."))
            return HttpResponseRedirect(
                reverse("admin:{}_{}_changelist".format(self.opts.app_label, self.opts.model_name))
            )

        ensure_media_dir()
        n_weeks = settings.GROUP_CHECKLIST_N_WEEKS
        n_members = settings.GROUP_CHECKLIST_N_MEMBERS

        context = {
            "groups": self.model.objects.filter(show_website=True),
            "settings": settings,
            "week_range": range(n_weeks),
            "member_range": range(n_members),
            "dates": mondays_until_nth(n_weeks),
            "weekdays": [long for i, long in WEEKDAYS],
            "header_text": settings.GROUP_CHECKLIST_TEXT,
        }
        return render_tex("Gruppen-Checkliste", "members/group_checklist.tex", context)


class ActivityCategoryAdmin(admin.ModelAdmin):
    fields = ["name", "ljp_category", "description"]


class FreizeitAdminForm(forms.ModelForm):
    difficulty = TypedChoiceField(
        choices=Freizeit.difficulty_choices, coerce=int, label=_("Difficulty")
    )
    tour_type = TypedChoiceField(
        choices=Freizeit.tour_type_choices, coerce=int, label=_("Tour type")
    )
    tour_approach = TypedChoiceField(
        choices=Freizeit.tour_approach_choices, coerce=int, label=_("Means of transportation")
    )

    class Meta:
        model = Freizeit
        exclude = ["add_member"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "jugendleiter" in self.fields:
            q = self.fields["jugendleiter"].queryset
            self.fields["jugendleiter"].queryset = q.filter(group__name="Jugendleiter")


class BillOnExcursionInline(CommonAdminInlineMixin, admin.TabularInline):
    model = BillOnExcursionProxy
    extra = 0
    sortable_options = []
    fields = ["short_description", "explanation", "amount", "paid_by", "proof"]
    formfield_overrides = {
        TextField: {"widget": Textarea(attrs={"rows": 1, "cols": 40})},
        RestrictedFileField: {
            "widget": forms.ClearableFileInput(
                attrs={"accept": "application/pdf,image/jpeg,image/png"}
            )
        },
    }


class StatementOnListForm(forms.ModelForm):
    """
    Form to edit a statement attached to an excursion. This is used in an inline on
    the excursion admin.
    """

    def __init__(self, *args, **kwargs):
        excursion = kwargs.pop("parent_obj")
        super().__init__(*args, **kwargs)
        # only allow youth leaders of this excursion to be selected as recipients
        # of subsidies and allowance
        self.fields["allowance_to"].queryset = excursion.jugendleiter.all()
        self.fields["subsidy_to"].queryset = excursion.jugendleiter.all()
        self.fields["ljp_to"].queryset = excursion.jugendleiter.all()

    class Meta:
        model = StatementOnExcursionProxy
        fields = ["night_cost", "allowance_to", "subsidy_to", "ljp_to"]

    def clean(self):
        """Check if the `allowance_to` and `subsidy_to` fields are compatible with
        the total number of approved youth leaders."""
        allowance_to = self.cleaned_data.get("allowance_to")
        excursion = self.cleaned_data.get("excursion")
        if allowance_to is None:
            return
        if allowance_to.count() > excursion.approved_staff_count:
            raise ValidationError(
                {
                    "allowance_to": _(
                        "This excursion only has up to %(approved_count)s approved youth leaders, but you listed %(entered_count)s."
                    )
                    % {
                        "approved_count": str(excursion.approved_staff_count),
                        "entered_count": str(allowance_to.count()),
                    },
                }
            )


class StatementOnListInline(CommonAdminInlineMixin, nested_admin.NestedStackedInline):
    model = StatementOnExcursionProxy
    extra = 1
    description = _(
        "Please list here all expenses in relation with this excursion and upload relevant bills. These have to be permanently stored for the application of LJP contributions. The short descriptions are used in the seminar report cost overview (possible descriptions are e.g. food, material, etc.)."
    )
    sortable_options = []
    fields = ["night_cost", "allowance_to", "subsidy_to", "ljp_to"]
    inlines = [BillOnExcursionInline]
    form = StatementOnListForm

    def get_formset(self, request, obj=None, **kwargs):
        BaseFormSet = kwargs.pop("formset", self.formset)

        class CustomFormSet(BaseFormSet):
            def get_form_kwargs(self, index):
                kwargs = super().get_form_kwargs(index)
                kwargs["parent_obj"] = obj
                return kwargs

        kwargs["formset"] = CustomFormSet
        return super().get_formset(request, obj, **kwargs)


class InterventionOnLJPInline(CommonAdminInlineMixin, admin.TabularInline):
    model = Intervention
    extra = 0
    sortable_options = []
    formfield_overrides = {TextField: {"widget": Textarea(attrs={"rows": 1, "cols": 80})}}


class LJPOnListInline(CommonAdminInlineMixin, nested_admin.NestedStackedInline):
    model = LJPProposal
    extra = 1
    description = _(
        "Here you can work on a seminar report for applying for financial contributions from Landesjugendplan (LJP). More information on creating a seminar report can be found in the wiki. The seminar report or only a participant list and cost overview can be consequently downloaded."
    )
    sortable_options = []
    inlines = [InterventionOnLJPInline]


class MemberOnListInlineForm(forms.ModelForm):
    """Custom form for the `MemberOnListInline`"""

    class Meta:
        model = NewMemberOnList
        exclude = []

    def __init__(self, *args, **kwargs):
        prefilled = kwargs.pop("prefilled", False)
        super().__init__(*args, **kwargs)
        # If prefilled is set, the inline received initial data.
        # We need to override the `has_changed` method of the `member` field, otherwise
        # the prefilled data is not saved.
        if prefilled:
            member_field = self.fields["member"]

            def new_has_changed(self, data):
                return data != ""

            member_field.has_changed = new_has_changed


class MemberOnListInline(CommonAdminInlineMixin, GenericTabularInline):
    model = NewMemberOnList
    extra = 0
    description = _(
        "Please list all participants (also youth leaders) of this excursion. Here you can still make changes just before departure and hence generate the latest participant list for crisis intervention at all times."
    )
    formfield_overrides = {TextField: {"widget": Textarea(attrs={"rows": 1, "cols": 40})}}
    sortable_options = []
    template = "admin/members/freizeit/memberonlistinline.html"
    form = MemberOnListInlineForm

    def people_count(self, obj):
        if isinstance(obj, Freizeit):
            # Number of organizers who are also in the Memberlist
            organizer_count = obj.staff_on_memberlist_count

            # Total number of people in the Memberlist
            total_people = obj.head_count

        else:  # fallback if no activity was found
            total_people = 0
            organizer_count = 0
        return dict(total_people=total_people, organizer_count=organizer_count)

    def get_formset(self, request, obj=None, **kwargs):
        """Override get_formset to add extra context and handle initial member data."""
        # Handle members query parameter for pre-populating members on add view
        initial_data = []
        if obj is None:  # Only for add view
            raw_members = request.GET.get("members", None)
            if raw_members is not None:
                try:
                    m_ids = json.loads(raw_members)
                    if isinstance(m_ids, list):
                        members = Member.objects.filter(pk__in=m_ids)
                        # Set extra forms to match number of members
                        self.extra = len(members)
                        # Prepare initial data for formset
                        initial_data = [{"member": member.pk} for member in members]
                except (json.JSONDecodeError, ValueError):
                    pass

        FormSet = super().get_formset(request, obj, **kwargs)

        if obj:  # Ensure there is an Activity instance
            FormSet.total_people = self.people_count(obj)["total_people"]
            FormSet.organizer_count = self.people_count(obj)["organizer_count"]

        # If we have initial data, create a wrapped formset class that uses it
        if initial_data:
            original_init = FormSet.__init__
            original_get_form_kwargs = FormSet.get_form_kwargs

            def new_init(self, *args, **init_kwargs):
                if "initial" not in init_kwargs:
                    init_kwargs["initial"] = initial_data
                original_init(self, *args, **init_kwargs)

            def new_get_form_kwargs(self, index):
                # we pass the prefilled kwarg to the `MemberOnListInlineForm`
                kwargs = original_get_form_kwargs(self, index)
                kwargs["prefilled"] = True
                return kwargs

            FormSet.__init__ = new_init
            FormSet.get_form_kwargs = new_get_form_kwargs

        return FormSet


class MemberNoteListAdmin(ExtraButtonsMixin, admin.ModelAdmin):
    inlines = [MemberOnListInline]
    list_display = ["__str__", "date"]
    search_fields = ("name",)
    ordering = ("-date",)

    @staticmethod
    def may_view_notelist(request, memberlist):
        return request.user.has_perm("members.view_global_member") or (
            hasattr(request.user, "member")
            and all(
                [request.user.member.may_view(m.member) for m in memberlist.membersonlist.all()]
            )
        )

    @extra_button(
        _("Generate PDF summary"),
        url_name="summary",
        method="POST",
        target="_blank",
        permission=may_view_notelist.__func__,
    )
    def summary(self, request, memberlist):
        context = dict(memberlist=memberlist, settings=settings)
        return render_tex(
            f"{memberlist.title}_Zusammenfassung",
            "members/notelist_summary.tex",
            context,
            date=memberlist.date,
        )

    summary.short_description = _("Generate PDF summary")


class GenerateSjrForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.attachments = kwargs.pop("attachments")

        super().__init__(*args, **kwargs)
        self.fields["invoice"] = forms.ChoiceField(choices=self.attachments, label=_("Invoice"))


def decorate_download(fun):
    def aux(self, request, object_id):
        try:
            memberlist = Freizeit.objects.get(pk=object_id)
        except Freizeit.DoesNotExist:
            messages.error(request, _("Excursion not found."))
            return HttpResponseRedirect(
                reverse("admin:{}_{}_changelist".format(self.opts.app_label, self.opts.model_name))
            )
        if not self.may_view_excursion(request, memberlist):
            return self.not_allowed_view(request, memberlist)
        if not hasattr(memberlist, "ljpproposal"):
            messages.error(
                request,
                _("This excursion does not have a LJP proposal. Please add one and try again."),
            )
            return HttpResponseRedirect(
                reverse(
                    "admin:{}_{}_change".format(self.opts.app_label, self.opts.model_name),
                    args=(memberlist.pk,),
                )
            )
        return fun(self, request, memberlist)

    return aux


class ParticipantFilter(admin.SimpleListFilter):
    """
    List filter on excursions: Returns excursions that the given member participated in.
    """

    title = _("Has participant")
    parameter_name = "has_participant"

    def lookups(self, request, model_admin):
        return [(m.pk, m.name) for m in Member.objects.all()]

    def queryset(self, request, queryset):
        pk = self.value()
        if not pk:
            return queryset
        return queryset.filter(Q(membersonlist__member__pk=pk) | Q(jugendleiter__pk=pk)).distinct()


class FreizeitAdmin(ExtraButtonsMixin, CommonAdminMixin, nested_admin.NestedModelAdmin):
    # inlines = [MemberOnListInline, LJPOnListInline, StatementOnListInline]
    form = FreizeitAdminForm
    list_display = ["__str__", "date", "place", "approved"]
    search_fields = ("name",)
    ordering = ("-date",)
    list_filter = [ParticipantFilter, "groups", "approved"]
    view_on_site = False
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "place",
                    "postcode",
                    "destination",
                    "date",
                    "end",
                    "description",
                    "groups",
                    "jugendleiter",
                    "activity",
                    "difficulty",
                    "tour_type",
                    "tour_approach",
                    "kilometers_traveled",
                ),
                "description": _(
                    "General information on your excursion. These are partly relevant for the amount of financial compensation (means of transport, travel distance, etc.)."
                ),
            },
        ),
        (
            _("Approval"),
            {
                "fields": ("approved", "approval_comments", "approved_extra_youth_leader_count"),
                "description": _(
                    "Information on the approval status of this excursion. Everything here is not editable by standard users."
                ),
            },
        ),
    )
    # formfield_overrides = {
    #    ManyToManyField: {'widget': forms.CheckboxSelectMultiple},
    #    ForeignKey: {'widget': apply_select2(forms.Select)}
    # }
    field_view_permissions = {
        "approved": "members.view_approval_excursion",
        "approval_comments": "members.view_approval_excursion",
    }

    field_change_permissions = {
        "approved": "members.manage_approval_excursion",
        "approval_comments": "members.manage_approval_excursion",
    }

    def get_inlines(self, request, obj=None):
        if obj:
            return [MemberOnListInline, LJPOnListInline, StatementOnListInline]
        else:
            return [MemberOnListInline]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def save_model(self, request, obj, form, change):
        if not change and hasattr(request.user, "member") and hasattr(obj, "statement"):
            obj.statement.created_by = request.user.member
            obj.statement.save()
        super().save_model(request, obj, form, change)

    @staticmethod
    def may_view_excursion(request, memberlist):
        return request.user.has_perm("members.view_global_member") or (
            hasattr(request.user, "member")
            and all(
                [request.user.member.may_view(m.member) for m in memberlist.membersonlist.all()]
            )
        )

    def not_allowed_view(self, request, memberlist):
        messages.error(
            request,
            _("You are not allowed to view all members on excursion %(name)s.")
            % {"name": memberlist.name},
        )
        return HttpResponseRedirect(
            reverse("admin:{}_{}_changelist".format(self.opts.app_label, self.opts.model_name))
        )

    @extra_button(
        _("Generate crisis intervention list"),
        method="POST",
        target="_blank",
        permission=may_view_excursion.__func__,
    )
    def crisis_intervention_list(self, request, memberlist):
        # Get all members on the list
        members = [mol.member for mol in memberlist.membersonlist.all()]

        # Generate PDF using shared function
        return generate_crisis_intervention_list_pdf(
            name=memberlist.name,
            description=memberlist.description,
            code=memberlist.code,
            place=memberlist.place,
            destination=memberlist.destination,
            groups=memberlist.groups.all(),
            staff=memberlist.jugendleiter.all(),
            start_date=memberlist.date,
            end_date=memberlist.end,
            tour_type=memberlist.get_tour_type_display(),
            tour_approach=memberlist.get_tour_approach_display(),
            members=members,
        )

    crisis_intervention_list.short_description = _("Generate crisis intervention list")

    @extra_button(
        _("Generate overview"),
        url_name="notes_list",
        method="POST",
        target="_blank",
        permission=may_view_excursion.__func__,
    )
    def notes_list(self, request, memberlist):
        people, skills = memberlist.skill_summary
        context = dict(memberlist=memberlist, people=people, skills=skills, settings=settings)
        return render_tex(
            f"{memberlist.code}_{memberlist.name}_Notizen",
            "members/notes_list.tex",
            context,
            date=memberlist.date,
        )

    notes_list.short_description = _("Generate overview")

    @decorate_download
    def download_seminar_vbk(self, request, memberlist):
        fp = generate_ljp_vbk(memberlist)
        return serve_media(fp, "application/xlsx")

    @decorate_download
    def download_seminar_report_docx(self, request, memberlist):
        title = memberlist.ljpproposal.title
        context = dict(memberlist=memberlist, settings=settings)
        return render_docx(
            f"{memberlist.code}_{title}_Seminarbericht",
            "members/seminar_report_docx.tex",
            context,
            date=memberlist.date,
        )

    @decorate_download
    def download_seminar_report_costs_and_participants(self, request, memberlist):
        title = memberlist.ljpproposal.title
        context = dict(memberlist=memberlist, settings=settings)
        return render_tex(
            f"{memberlist.code}_{title}_TN_Kosten",
            "members/seminar_report.tex",
            context,
            date=memberlist.date,
        )

    @extra_button(
        _("Generate seminar report"), method="POST", permission=may_view_excursion.__func__
    )
    def seminar_report(self, request, memberlist):
        if not hasattr(memberlist, "ljpproposal"):
            messages.error(
                request,
                _("This excursion does not have a LJP proposal. Please add one and try again."),
            )
            return HttpResponseRedirect(
                reverse(
                    "admin:{}_{}_change".format(self.opts.app_label, self.opts.model_name),
                    args=(memberlist.pk,),
                )
            )
        context = dict(
            self.admin_site.each_context(request),
            title=_("Generate seminar report"),
            opts=self.opts,
            memberlist=memberlist,
            object=memberlist,
        )
        return render(request, "admin/generate_seminar_report.html", context=context)

    seminar_report.short_description = _("Generate seminar report")

    def render_sjr_options(self, request, memberlist, form):
        context = dict(
            self.admin_site.each_context(request),
            title=_("Generate SJR application"),
            opts=self.opts,
            memberlist=memberlist,
            form=form,
            object=memberlist,
        )
        return render(request, "admin/generate_sjr_application.html", context=context)

    @extra_button(
        _("Generate SJR application"), method="POST", permission=may_view_excursion.__func__
    )
    def sjr_application(self, request, memberlist):
        if hasattr(memberlist, "statement"):
            attachment_names = [
                f"{b.short_description}: {b.explanation} ({b.amount:.2f}€)"
                for b in memberlist.statement.bill_set.all()
                if b.proof
            ]
            attachment_paths = [
                b.proof.path for b in memberlist.statement.bill_set.all() if b.proof
            ]
        else:
            attachment_names = []
            attachment_paths = []
        attachments = zip(attachment_paths, attachment_names)

        if "apply" in request.POST:
            form = GenerateSjrForm(request.POST, attachments=attachments)
            if not form.is_valid():
                messages.error(request, _("Please select an invoice."))
                return self.render_sjr_options(request, memberlist, form)

            selected_attachments = [form.cleaned_data["invoice"]]
            context = memberlist.sjr_application_fields()
            title = (
                memberlist.ljpproposal.title
                if hasattr(memberlist, "ljpproposal")
                else memberlist.name
            )

            return fill_pdf_form(
                f"{memberlist.code}_{title}_SJR_Antrag",
                "members/sjr_template.pdf",
                context,
                selected_attachments,
                date=memberlist.date,
            )

        return self.render_sjr_options(
            request, memberlist, GenerateSjrForm(attachments=attachments)
        )

    sjr_application.short_description = _("Generate SJR application")

    @extra_button(
        _("Finance overview"),
        method="POST",
        condition=lambda obj: hasattr(obj, "statement"),
    )
    def finance_overview(self, request, memberlist):
        if not hasattr(memberlist, "statement"):
            messages.error(request, _("No statement found. Please add a statement and then retry."))
            return HttpResponseRedirect(
                reverse(
                    "admin:{}_{}_change".format(self.opts.app_label, self.opts.model_name),
                    args=(memberlist.pk,),
                )
            )
        if "apply" in request.POST:
            if not memberlist.statement.allowance_to_valid:
                messages.error(
                    request,
                    _(
                        "The configured recipients of the allowance don't match the regulations. Please correct this and try again."
                    ),
                )
                return HttpResponseRedirect(
                    reverse(
                        "admin:{}_{}_change".format(self.opts.app_label, self.opts.model_name),
                        args=(memberlist.pk,),
                    )
                )

            if memberlist.statement.ljp_to and len(memberlist.statement.bills_without_proof) > 0:
                messages.error(
                    request,
                    _(
                        "The excursion is configured to claim LJP contributions. In that case, for all bills, a proof must be uploaded. Please correct this and try again."
                    ),
                )
                return HttpResponseRedirect(
                    reverse(
                        "admin:{}_{}_change".format(self.opts.app_label, self.opts.model_name),
                        args=(memberlist.pk,),
                    )
                )

            memberlist.statement.submit(get_member(request))
            messages.success(
                request,
                _(
                    "Successfully submited statement. The finance department will notify you as soon as possible."
                ),
            )
            return HttpResponseRedirect(
                reverse(
                    "admin:{}_{}_change".format(self.opts.app_label, self.opts.model_name),
                    args=(memberlist.pk,),
                )
            )
        context = dict(
            self.admin_site.each_context(request),
            title=_("Finance overview"),
            opts=self.opts,
            memberlist=memberlist,
            object=memberlist,
            ljp_contributions=memberlist.payable_ljp_contributions,
            total_relative_costs=memberlist.total_relative_costs,
            **memberlist.statement.template_context(),
        )
        return render(request, "admin/freizeit_finance_overview.html", context=context)

    # TODO: can this be integrated into the extra_button's framework?
    def get_urls(self):
        urls = super().get_urls()

        def wrap(view):
            def wrapper(*args, **kwargs):
                return self.admin_site.admin_view(view)(*args, **kwargs)

            wrapper.model_admin = self
            return update_wrapper(wrapper, view)

        custom_urls = [
            path(
                "<path:object_id>/download/ljp_vbk",
                wrap(self.download_seminar_vbk),
                name="{}_{}_download_ljp_vbk".format(self.opts.app_label, self.opts.model_name),
            ),
            path(
                "<path:object_id>/download/ljp_report_docx",
                wrap(self.download_seminar_report_docx),
                name="{}_{}_download_ljp_report_docx".format(
                    self.opts.app_label, self.opts.model_name
                ),
            ),
            path(
                "<path:object_id>/download/ljp_report_costs_and_participants",
                wrap(self.download_seminar_report_costs_and_participants),
                name="{}_{}_download_ljp_costs_participants".format(
                    self.opts.app_label, self.opts.model_name
                ),
            ),
        ]
        return custom_urls + urls


class KlettertreffAdminForm(forms.ModelForm):
    class Meta:
        model = Klettertreff
        exclude = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["jugendleiter"].queryset = Member.objects.filter(group__name="Jugendleiter")


class KlettertreffAttendeeInlineForm(forms.ModelForm):
    class Meta:
        model = KlettertreffAttendee
        exclude = []

    """
    def __init__(self, *args, **kwargs):
        super(KlettertreffAttendeeInlineForm, self).__init__(*args, **kwargs)
        self.fields['member'].queryset = Member.objects.filter(group__name='J1')
    """


class KlettertreffAttendeeInline(admin.TabularInline):
    model = KlettertreffAttendee
    form = KlettertreffAttendeeInlineForm
    extra = 0
    # formfield_overrides = {
    #    ManyToManyField: {'widget': forms.CheckboxSelectMultiple},
    #    ForeignKey: {'widget': apply_select2(forms.Select)}
    # }


class KlettertreffAdmin(admin.ModelAdmin):
    form = KlettertreffAdminForm
    exclude = []
    inlines = [KlettertreffAttendeeInline]
    list_display = ["__str__", "date", "get_jugendleiter"]
    search_fields = ("date", "location", "topic")
    list_filter = [("date", DateFieldListFilter), "group"]
    actions = ["overview"]

    def overview(self, request, queryset):
        group = request.GET.get("group__id__exact")
        if group is not None:
            members = Member.objects.filter(group=group)
        else:
            members = Member.objects.all()
        context = {
            "klettertreffs": queryset,
            "members": members,
            "attendees": KlettertreffAttendee.objects.all(),
            "jugendleiters": Member.objects.filter(group__name="Jugendleiter"),
        }

        return render(request, "admin/klettertreff_overview.html", context)

    # formfield_overrides = {
    #    ManyToManyField: {'widget': forms.CheckboxSelectMultiple},
    #    ForeignKey: {'widget': apply_select2(forms.Select)}
    # }


class MemberTrainingAdminForm(forms.ModelForm):
    class Meta:
        model = MemberTraining
        exclude = []


class MemberTrainingAdmin(CommonAdminMixin, nested_admin.NestedModelAdmin):
    form = MemberTrainingAdminForm
    list_display = [
        "title",
        "member",
        "date",
        "category",
        "get_activities",
        "participated",
        "passed",
        "certificate",
    ]
    search_fields = ["title"]
    list_filter = (("date", DateFieldListFilter), "category", "passed", "activity", "member")
    ordering = ("-date",)


admin.site.register(Member, MemberAdmin)
admin.site.register(MemberUnconfirmedProxy, MemberUnconfirmedAdmin)
admin.site.register(MemberWaitingList, MemberWaitingListAdmin)
admin.site.register(Group, GroupAdmin)
admin.site.register(Freizeit, FreizeitAdmin)
admin.site.register(MemberNoteList, MemberNoteListAdmin)
admin.site.register(Klettertreff, KlettertreffAdmin)
admin.site.register(ActivityCategory, ActivityCategoryAdmin)
admin.site.register(TrainingCategory, TrainingCategoryAdmin)
admin.site.register(MemberTraining, MemberTrainingAdmin)
