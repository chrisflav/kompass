"""Read and write schemas for the startpage API.

The ``*Brief`` schemas are the compact identity representation returned by list
endpoints; the richer ``*Out`` schemas carry the full detail served by retrieve
endpoints. ``id`` (and every always-present ``date``) is declared explicitly so
``ModelSchema`` types it as a required, non-null value instead of an optional
one.
"""

import datetime

from members.api.schemas import GroupBrief
from members.api.schemas import MemberBrief
from members.models import Group
from members.models import Member
from ninja import ModelSchema
from ninja import Schema
from startpage.models import FAQ
from startpage.models import Image
from startpage.models import Link
from startpage.models import MemberOnPost
from startpage.models import Post
from startpage.models import Section

# --- sections -------------------------------------------------------------


class SectionBrief(ModelSchema):
    id: int
    absolute_urlname: str

    class Meta:
        model = Section
        fields = ["title", "urlname", "show_in_navigation"]

    @staticmethod
    def resolve_absolute_urlname(obj) -> str:
        return str(obj.absolute_urlname())


class SectionOut(ModelSchema):
    id: int
    absolute_urlname: str

    class Meta:
        model = Section
        fields = ["title", "urlname", "website_text", "show_in_navigation"]

    @staticmethod
    def resolve_absolute_urlname(obj) -> str:
        return str(obj.absolute_urlname())


class SectionIn(Schema):
    title: str
    urlname: str
    website_text: str = ""
    show_in_navigation: bool = True


# --- posts ----------------------------------------------------------------


class PostBrief(ModelSchema):
    id: int
    date: datetime.date | None = None
    section_id: int | None = None
    section_title: str | None = None
    # The section's url segment, so a list row can link to the SPA route
    # (/beitrag/<section>/<post>) instead of showing the legacy Django path.
    section_urlname: str | None = None
    absolute_urlname: str

    class Meta:
        model = Post
        fields = ["title", "urlname", "detailed"]

    @staticmethod
    def resolve_section_urlname(obj) -> str | None:
        return obj.section.urlname if obj.section else None

    @staticmethod
    def resolve_section_title(obj) -> str | None:
        # Mirrors the admin ``section`` list column (Section.__str__ == title);
        # None when the post has no section, exactly like the admin.
        return obj.section.title if obj.section else None

    @staticmethod
    def resolve_absolute_urlname(obj) -> str:
        return str(obj.absolute_urlname())


class PostOut(ModelSchema):
    id: int
    date: datetime.date | None = None
    absolute_section: str
    absolute_urlname: str
    section: SectionBrief | None = None
    groups: list[GroupBrief]

    class Meta:
        model = Post
        fields = ["title", "urlname", "website_text", "detailed"]

    @staticmethod
    def resolve_absolute_section(obj) -> str:
        return str(obj.absolute_section())

    @staticmethod
    def resolve_absolute_urlname(obj) -> str:
        return str(obj.absolute_urlname())

    @staticmethod
    def resolve_groups(obj):
        return obj.groups.all()


class PostIn(Schema):
    title: str = ""
    urlname: str = ""
    date: datetime.date | None = None
    website_text: str = ""
    detailed: bool = False
    section_id: int | None = None
    group_ids: list[int] = []


# --- faqs -----------------------------------------------------------------


class FAQBrief(ModelSchema):
    id: int

    class Meta:
        model = FAQ
        fields = ["question"]


class FAQOut(ModelSchema):
    id: int

    class Meta:
        model = FAQ
        fields = ["question", "answer"]


class FAQIn(Schema):
    question: str
    answer: str


# --- links ----------------------------------------------------------------


class LinkBrief(ModelSchema):
    id: int

    class Meta:
        model = Link
        fields = ["title", "url", "visible"]


class LinkOut(ModelSchema):
    id: int
    icon: str | None = None

    class Meta:
        model = Link
        fields = ["title", "description", "url", "visible"]

    @staticmethod
    def resolve_icon(obj) -> str | None:
        return obj.icon.url if obj.icon else None


class LinkIn(Schema):
    title: str = ""
    description: str = ""
    url: str
    visible: bool = True


# --- images ---------------------------------------------------------------


class ImageOut(ModelSchema):
    id: int
    post_id: int
    name: str
    f: str | None = None

    class Meta:
        model = Image
        exclude = ["post", "f"]

    @staticmethod
    def resolve_name(obj) -> str:
        return str(obj)

    @staticmethod
    def resolve_f(obj) -> str | None:
        return obj.f.url if obj.f else None


# --- members on posts -----------------------------------------------------


class MemberOnPostBrief(ModelSchema):
    id: int
    post_id: int

    class Meta:
        model = MemberOnPost
        fields = ["tag"]


class MemberOnPostOut(ModelSchema):
    id: int
    post_id: int
    members: list[MemberBrief]

    class Meta:
        model = MemberOnPost
        fields = ["description", "tag"]

    @staticmethod
    def resolve_members(obj):
        return obj.members.all()


class MemberOnPostIn(Schema):
    post_id: int
    description: str = ""
    tag: str = ""
    member_ids: list[int] = []


# --- public read schemas --------------------------------------------------
#
# These mirror the unauthenticated public website views (``startpage/views.py``)
# so the SPA can render the entire public site from the API. They intentionally
# expose only the fields the corresponding templates render — no member contact
# data or hidden groups leak through the public surface.


class PublicMemberBrief(ModelSchema):
    """A person as shown in a public portrait grid (name + optional photo)."""

    id: int
    name: str
    image: str | None = None

    class Meta:
        model = Member
        fields = ["prename", "lastname"]

    @staticmethod
    def resolve_image(obj) -> str | None:
        return obj.image.url if obj.image else None


class PublicPostBrief(ModelSchema):
    """Compact post representation for the index / aktuelles / berichte listings.

    Includes ``website_text`` because those listings render a truncated preview.
    """

    id: int
    date: datetime.date | None = None
    section_id: int | None = None
    # The section's urlname, so the SPA can build the post-detail link
    # (/beitrag/<section_urlname>/<urlname>) without a second lookup.
    section_urlname: str = ""
    # The post's first image, used as the lead picture in the public listings.
    # Posts have carried images all along; no public schema exposed them, so the
    # whole public site rendered text-only.
    image: str | None = None

    class Meta:
        model = Post
        fields = ["title", "urlname", "website_text", "detailed"]

    @staticmethod
    def resolve_image(obj) -> str | None:
        first = next(iter(obj.image_set.all()), None)
        return first.f.url if first and first.f else None

    @staticmethod
    def resolve_section_urlname(obj) -> str:
        return obj.section.urlname if obj.section_id else ""


class PublicMemberOnPost(Schema):
    """A tagged group of people credited on a post (``MemberOnPost``)."""

    id: int
    description: str = ""
    tag: str = ""
    members: list[PublicMemberBrief]

    @staticmethod
    def resolve_members(obj):
        return obj.members.all()


class PublicPostDetail(ModelSchema):
    """Full public post detail served by the ``section_name/post_name`` route."""

    id: int
    date: datetime.date | None = None
    section: SectionBrief | None = None
    people_on_post: list[PublicMemberOnPost]
    people: list[PublicMemberBrief]

    class Meta:
        model = Post
        fields = ["title", "urlname", "website_text", "detailed"]

    @staticmethod
    def resolve_people_on_post(obj):
        return obj.people.all()

    @staticmethod
    def resolve_people(obj):
        return [m for group in obj.groups.all() for m in group.member_set.all()]


class PublicGroupBrief(Schema):
    """A group as listed on the public ``gruppen`` page and in the navigation."""

    id: int
    name: str


class PublicGroupDetail(ModelSchema):
    """Public group detail mirroring ``startpage/gruppen/detail.html``.

    The ``show_website_*`` flags let the SPA reproduce the template's conditional
    display of age / weekday / time / contact-email / registration link exactly.
    """

    id: int
    age_info: str
    has_age_info: bool
    weekday_display: str
    time_slot: str
    contact_email: str | None = None
    has_registration_password: bool
    people: list[PublicMemberBrief]

    class Meta:
        model = Group
        fields = [
            "name",
            "description",
            "show_website_year",
            "show_website_weekday",
            "show_website_time",
            "show_website_contact_email",
            "show_website_registration",
        ]

    @staticmethod
    def resolve_age_info(obj) -> str:
        return obj.get_age_info()

    @staticmethod
    def resolve_has_age_info(obj) -> bool:
        return bool(obj.has_age_info())

    @staticmethod
    def resolve_weekday_display(obj) -> str:
        return obj.get_weekday_display_info()

    @staticmethod
    def resolve_time_slot(obj) -> str:
        return obj.get_time_slot_info()

    @staticmethod
    def resolve_contact_email(obj) -> str | None:
        return obj.contact_email.email if obj.contact_email else None

    @staticmethod
    def resolve_has_registration_password(obj) -> bool:
        return bool(obj.has_registration_password())

    @staticmethod
    def resolve_people(obj):
        return obj.leiters.all()


class PublicSiteOut(Schema):
    """Who is running this deployment: the section's identity and imprint data.

    Read straight from ``settings.SEKTION*`` (the ``[section]`` table of
    ``settings.toml``). The SPA is deployed per section, so every place that
    names the section — the wordmark, the page titles, the imprint — reads it
    from here instead of carrying one section's name in its source.
    """

    name: str
    # ``JDAV <name>``, so the wordmark is spelled in exactly one place.
    display_name: str
    dav_section: str
    street: str
    town: str
    telephone: str
    telefax: str
    contact_mail: str
    board_mail: str
    responsible_mail: str
    # Both null unless the deployment configured them; the hero drops its
    # coordinate readout rather than inventing a location.
    latitude: float | None = None
    longitude: float | None = None


class NavigationOut(Schema):
    """Shared navigation context injected on every public page (``render``)."""

    sections: list[SectionBrief]
    groups: list[PublicGroupBrief]
    root_section: SectionOut | None = None


class IndexOut(Schema):
    """Landing-page content: the most recent news posts and reports."""

    recent_posts: list[PublicPostBrief]
    reports: list[PublicPostBrief]


class SectionPostsOut(Schema):
    """A section together with all of its posts (aktuelles / berichte pages)."""

    section: SectionOut
    posts: list[PublicPostBrief]
