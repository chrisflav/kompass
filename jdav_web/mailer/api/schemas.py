"""Read/write schemas for the mailer API.

Mirrors the members API contract: list rows use a compact ``*Brief`` schema
while detail endpoints serve the richer ``*Out`` schema. ``id`` (and any
always-present relation) is declared explicitly because ``ModelSchema`` would
otherwise mark the ``AutoField`` optional/nullable.
"""

from mailer.models import EmailAddress
from mailer.models import Message
from members.api.schemas import ExcursionBrief
from members.api.schemas import GroupBrief
from members.api.schemas import MemberBrief
from ninja import ModelSchema
from ninja import Schema


class UnsubscribeInfo(Schema):
    """Public unsubscribe context: the address that will be / was unsubscribed."""

    name: str
    email: str


class UnsubscribeIn(Schema):
    """Confirm-unsubscribe payload carrying the per-member secret key."""

    key: str


class EmailAddressBrief(ModelSchema):
    id: int
    email: str

    class Meta:
        model = EmailAddress
        fields = ["name", "internal_only"]

    @staticmethod
    def resolve_email(obj) -> str:
        return obj.email


class EmailAddressOut(ModelSchema):
    id: int
    email: str
    forwards: list[str]
    to_members: list[MemberBrief]
    to_groups: list[GroupBrief]
    allowed_senders: list[GroupBrief]

    class Meta:
        model = EmailAddress
        fields = ["name", "internal_only"]

    @staticmethod
    def resolve_email(obj) -> str:
        return obj.email

    @staticmethod
    def resolve_forwards(obj) -> list[str]:
        return sorted(obj.forwards)

    @staticmethod
    def resolve_to_members(obj):
        return obj.to_members.all()

    @staticmethod
    def resolve_to_groups(obj):
        return obj.to_groups.all()

    @staticmethod
    def resolve_allowed_senders(obj):
        return obj.allowed_senders.all()


class EmailAddressIn(Schema):
    """Write payload for creating/updating a forwarding alias."""

    name: str
    internal_only: bool = False
    to_members: list[int] = []
    to_groups: list[int] = []
    allowed_senders: list[int] = []


class AttachmentOut(Schema):
    id: int
    message_id: int
    filename: str
    url: str | None = None

    @staticmethod
    def resolve_message_id(obj) -> int:
        return obj.msg_id

    @staticmethod
    def resolve_filename(obj) -> str:
        return str(obj)

    @staticmethod
    def resolve_url(obj) -> str | None:
        return obj.f.url if obj.f and obj.f.name else None


class MessageBrief(ModelSchema):
    id: int
    recipients: str

    class Meta:
        model = Message
        fields = ["subject", "sent"]

    @staticmethod
    def resolve_recipients(obj) -> str:
        return obj.get_recipients()


class MessageOut(ModelSchema):
    id: int
    recipients: str
    created_by: MemberBrief | None = None
    to_freizeit: ExcursionBrief | None = None
    to_groups: list[GroupBrief]
    to_members: list[MemberBrief]
    reply_to: list[MemberBrief]
    reply_to_email_address: list[EmailAddressBrief]
    attachments: list[AttachmentOut]

    class Meta:
        model = Message
        fields = ["subject", "content", "sent"]

    @staticmethod
    def resolve_recipients(obj) -> str:
        return obj.get_recipients()

    @staticmethod
    def resolve_to_groups(obj):
        return obj.to_groups.all()

    @staticmethod
    def resolve_to_members(obj):
        return obj.to_members.all()

    @staticmethod
    def resolve_reply_to(obj):
        return obj.reply_to.all()

    @staticmethod
    def resolve_reply_to_email_address(obj):
        return obj.reply_to_email_address.all()

    @staticmethod
    def resolve_attachments(obj):
        return obj.attachment_set.all()


class MessageIn(Schema):
    """Write payload for composing a message.

    Only unsent messages are editable (see ``Message.filter_queryset_by_change_permissions``).
    ``created_by`` is set server-side from the authenticated member.
    """

    subject: str
    content: str
    to_groups: list[int] = []
    to_members: list[int] = []
    to_freizeit: int | None = None
    reply_to: list[int] = []
    reply_to_email_address: list[int] = []
