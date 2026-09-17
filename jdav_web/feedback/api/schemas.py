"""Schemas for the feedback API."""

import datetime

from feedback.models import Feedback
from members.api.schemas import MemberBrief
from ninja import ModelSchema
from ninja import Schema


class FeedbackIn(Schema):
    """One submission from the feedback dialog.

    ``page_url`` and ``user_agent`` arrive only when the sender ticked "send the
    current page"; both are optional and default to empty.
    """

    message: str
    page_url: str = ""
    user_agent: str = ""


class FeedbackBrief(ModelSchema):
    """A row in the feedback list."""

    id: int
    created: datetime.datetime
    submitted_by: MemberBrief | None = None
    has_context: bool

    class Meta:
        model = Feedback
        fields = ["message", "page_url"]


class FeedbackOut(ModelSchema):
    """Full feedback detail."""

    id: int
    created: datetime.datetime
    submitted_by: MemberBrief | None = None
    has_context: bool

    class Meta:
        model = Feedback
        fields = ["message", "page_url", "user_agent"]
