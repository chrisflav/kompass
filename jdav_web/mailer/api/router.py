"""Mailer API routes.

Permission model:

* ``EmailAddress`` is a plain ``django.db.models.Model`` with the default Django
  permissions, so it is gated with the standard ``view/add/change/delete``
  codenames (no ``scope_queryset`` — there is no member/row scoping for it).
* ``Message`` and ``Attachment`` subclass ``contrib.models.CommonModel`` and use
  the custom object-level rules: list via ``scope_queryset`` (creator-scoped),
  detail/change/delete via ``get_authorized(... "mailer.<verb>_obj_message")`` and
  create via ``authorize(... "mailer.add_global_message")``.

Attachment writes are authorized through their parent ``Message`` (matching the
admin, where attachments are edited inline in the message change view), so the
same ``change_obj_message`` predicate guards them.
"""

from contrib.api.perms import authorize
from contrib.api.perms import Forbidden
from contrib.api.perms import get_authorized
from contrib.api.perms import get_member
from contrib.permissions import scope_queryset
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from mailer.models import Attachment
from mailer.models import EmailAddress
from mailer.models import Message
from ninja import File
from ninja import Router
from ninja.files import UploadedFile
from utils import file_size_validator

from .schemas import AttachmentOut
from .schemas import EmailAddressBrief
from .schemas import EmailAddressIn
from .schemas import EmailAddressOut
from .schemas import MessageBrief
from .schemas import MessageIn
from .schemas import MessageOut

router = Router()


# --- email addresses (plain model, default Django perms) ------------------


@router.get("/email-addresses", response=list[EmailAddressBrief])
def list_email_addresses(request):
    """Forwarding aliases (plain ``mailer.view_emailaddress`` perm, no scoping)."""
    authorize(request, "mailer.view_emailaddress")
    return EmailAddress.objects.all().order_by("name")


@router.get("/email-addresses/{address_id}", response=EmailAddressOut)
def retrieve_email_address(request, address_id: int):
    """Full alias detail with computed ``email`` and ``forwards``."""
    authorize(request, "mailer.view_emailaddress")
    return get_object_or_404(EmailAddress, pk=address_id)


def _apply_email_address(address, payload):
    if not payload.to_members and not payload.to_groups:
        raise ValidationError(
            _("Either a group or at least one member is required as forward recipient.")
        )
    address.name = payload.name
    address.internal_only = payload.internal_only
    address.full_clean(exclude=["id"])
    address.save()
    address.to_members.set(payload.to_members)
    address.to_groups.set(payload.to_groups)
    address.allowed_senders.set(payload.allowed_senders)
    return address


@router.post("/email-addresses", response=EmailAddressOut)
def create_email_address(request, payload: EmailAddressIn):
    """Create a forwarding alias (``mailer.add_emailaddress``)."""
    authorize(request, "mailer.add_emailaddress")
    return _apply_email_address(EmailAddress(), payload)


@router.put("/email-addresses/{address_id}", response=EmailAddressOut)
def update_email_address(request, address_id: int, payload: EmailAddressIn):
    """Update a forwarding alias (``mailer.change_emailaddress``)."""
    authorize(request, "mailer.change_emailaddress")
    address = get_object_or_404(EmailAddress, pk=address_id)
    return _apply_email_address(address, payload)


@router.delete("/email-addresses/{address_id}", response={204: None})
def delete_email_address(request, address_id: int):
    """Delete a forwarding alias (``mailer.delete_emailaddress``)."""
    authorize(request, "mailer.delete_emailaddress")
    address = get_object_or_404(EmailAddress, pk=address_id)
    address.delete()
    return 204, None


# --- messages (CommonModel, custom object perms) --------------------------


@router.get("/messages", response=list[MessageBrief])
def list_messages(request):
    """Messages the user may list, creator-scoped by the shared permission filter."""
    return scope_queryset(request.user, Message.objects.all().order_by("-id"), model=Message)


@router.get("/messages/{message_id}", response=MessageOut)
def retrieve_message(request, message_id: int):
    """Full message detail, authorized per object."""
    return get_authorized(request, Message, message_id, "mailer.view_obj_message")


def _apply_message(message, payload):
    if not payload.to_groups and not payload.to_members and payload.to_freizeit is None:
        raise ValidationError(
            _("Either a group, a memberlist or at least one member is required as recipient")
        )
    message.subject = payload.subject
    message.content = payload.content
    message.to_freizeit_id = payload.to_freizeit
    message.save()
    message.to_groups.set(payload.to_groups)
    message.to_members.set(payload.to_members)
    message.reply_to.set(payload.reply_to)
    message.reply_to_email_address.set(payload.reply_to_email_address)
    return message


@router.post("/messages", response=MessageOut)
def create_message(request, payload: MessageIn):
    """Compose a message; ``created_by`` is bound to the authenticated member."""
    authorize(request, "mailer.add_global_message")
    message = Message(created_by=get_member(request))
    return _apply_message(message, payload)


@router.put("/messages/{message_id}", response=MessageOut)
def update_message(request, message_id: int, payload: MessageIn):
    """Update an unsent message, authorized per object."""
    message = get_authorized(request, Message, message_id, "mailer.change_obj_message")
    if message.sent:
        raise Forbidden(_("A sent message can no longer be edited."))
    return _apply_message(message, payload)


@router.delete("/messages/{message_id}", response={204: None})
def delete_message(request, message_id: int):
    """Delete a message, authorized per object."""
    message = get_authorized(request, Message, message_id, "mailer.delete_obj_message")
    message.delete()
    return 204, None


@router.post("/messages/{message_id}/submit", response=MessageOut)
def submit_message(request, message_id: int):
    """Send the message to its recipients (reproduces admin ``submit_message``).

    Requires the caller to be a member with an internal email address, then
    delegates to ``Message.submit`` — this actually dispatches the emails and
    deletes the attachments. The email/state logic is never reimplemented here.
    """
    message = get_authorized(request, Message, message_id, "mailer.change_obj_message")
    sender = get_member(request)
    if not sender.has_internal_email():
        raise Forbidden(
            _("Your email address is not an internal email address and may not send messages.")
        )
    message.submit(sender)
    return message


# --- attachments (authorized through their parent message) ----------------


@router.get("/messages/{message_id}/attachments", response=list[AttachmentOut])
def list_attachments(request, message_id: int):
    """List a message's attachments (gated on ``view_obj_message``)."""
    message = get_authorized(request, Message, message_id, "mailer.view_obj_message")
    return message.attachment_set.all()


@router.post("/messages/{message_id}/attachments", response=AttachmentOut)
def create_attachment(request, message_id: int, f: UploadedFile = File(...)):
    """Attach an uploaded file to an unsent message.

    Reproduces ``RestrictedFileField(max_upload_size=10)`` by reusing the shared
    ``file_size_validator`` (10 MiB cap).
    """
    message = get_authorized(request, Message, message_id, "mailer.change_obj_message")
    if message.sent:
        raise Forbidden(_("A sent message can no longer be edited."))
    file_size_validator(10)(f)
    return Attachment.objects.create(msg=message, f=f)


@router.delete("/attachments/{attachment_id}", response={204: None})
def delete_attachment(request, attachment_id: int):
    """Delete an attachment (authorized through its parent message)."""
    attachment = get_object_or_404(Attachment, pk=attachment_id)
    get_authorized(request, Message, attachment.msg_id, "mailer.change_obj_message")
    attachment.delete()
    return 204, None
