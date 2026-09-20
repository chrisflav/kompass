"""Startpage API routes.

All startpage models are plain ``django.db.models.Model`` instances using the
default Django permission set, so access is gated with standard
``startpage.<verb>_<model>`` permissions via :func:`contrib.api.perms.authorize`
(no member/row-level ``scope_queryset`` applies to this content).

File-carrying fields (``Image.f`` and ``Link.icon``) use ``RestrictedFileField``;
their upload endpoints reproduce that field's size and content-type constraints.
"""

from contrib.api.perms import authorize
from contrib.api.perms import set_scalar_fields
from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from members.models import Group
from ninja import File
from ninja import Form
from ninja import Router
from ninja.files import UploadedFile
from startpage.models import FAQ
from startpage.models import Image
from startpage.models import Link
from startpage.models import MemberOnPost
from startpage.models import Post
from startpage.models import Section

from .schemas import FAQBrief
from .schemas import FAQIn
from .schemas import FAQOut
from .schemas import ImageOut
from .schemas import IndexOut
from .schemas import LinkBrief
from .schemas import LinkIn
from .schemas import LinkOut
from .schemas import MemberOnPostBrief
from .schemas import MemberOnPostIn
from .schemas import MemberOnPostOut
from .schemas import NavigationOut
from .schemas import PostBrief
from .schemas import PostIn
from .schemas import PostOut
from .schemas import PublicGroupBrief
from .schemas import PublicGroupDetail
from .schemas import PublicPostDetail
from .schemas import PublicSiteOut
from .schemas import SectionBrief
from .schemas import SectionIn
from .schemas import SectionOut
from .schemas import SectionPostsOut

router = Router()


def _validate_upload(upload, max_upload_size, content_types=None):
    """Reproduce ``RestrictedFileField`` validation for an uploaded file.

    ``max_upload_size`` is the limit in MiB (as declared on the model field).
    """
    if content_types is not None and upload.content_type not in content_types:
        raise ValidationError(_("Filetype not supported."))
    limit = max_upload_size * 1024 * 1024
    if upload.size > limit:
        raise ValidationError(
            _("Please keep filesize under {} MiB. Current filesize: {:10.2f} MiB.").format(
                max_upload_size, upload.size / 1024 / 1024
            )
        )


# --- sections -------------------------------------------------------------


@router.get("/sections", response=list[SectionBrief])
def list_sections(request):
    authorize(request, "startpage.view_section")
    return Section.objects.all().order_by("title")


@router.post("/sections", response=SectionOut)
def create_section(request, payload: SectionIn):
    authorize(request, "startpage.add_section")
    section = Section(**payload.dict())
    section.full_clean()
    section.save()
    return section


@router.get("/sections/{section_id}", response=SectionOut)
def retrieve_section(request, section_id: int):
    authorize(request, "startpage.view_section")
    return get_object_or_404(Section, pk=section_id)


@router.put("/sections/{section_id}", response=SectionOut)
def update_section(request, section_id: int, payload: SectionIn):
    authorize(request, "startpage.change_section")
    section = get_object_or_404(Section, pk=section_id)
    data = payload.dict()
    set_scalar_fields(section, data, list(data.keys()))
    section.full_clean()
    section.save()
    return section


@router.delete("/sections/{section_id}")
def delete_section(request, section_id: int):
    authorize(request, "startpage.delete_section")
    section = get_object_or_404(Section, pk=section_id)
    section.delete()
    return {"success": True}


# --- posts ----------------------------------------------------------------


@router.get("/posts", response=list[PostBrief])
def list_posts(request):
    authorize(request, "startpage.view_post")
    return Post.objects.all().order_by("-date")


@router.post("/posts", response=PostOut)
def create_post(request, payload: PostIn):
    authorize(request, "startpage.add_post")
    data = payload.dict()
    group_ids = data.pop("group_ids")
    post = Post(**data)
    post.full_clean()
    post.save()
    post.groups.set(group_ids)
    return post


@router.get("/posts/{post_id}", response=PostOut)
def retrieve_post(request, post_id: int):
    authorize(request, "startpage.view_post")
    return get_object_or_404(Post, pk=post_id)


@router.put("/posts/{post_id}", response=PostOut)
def update_post(request, post_id: int, payload: PostIn):
    authorize(request, "startpage.change_post")
    post = get_object_or_404(Post, pk=post_id)
    data = payload.dict()
    group_ids = data.pop("group_ids")
    set_scalar_fields(post, data, list(data.keys()))
    post.full_clean()
    post.save()
    post.groups.set(group_ids)
    return post


@router.delete("/posts/{post_id}")
def delete_post(request, post_id: int):
    authorize(request, "startpage.delete_post")
    post = get_object_or_404(Post, pk=post_id)
    post.delete()
    return {"success": True}


# --- faqs -----------------------------------------------------------------


@router.get("/faqs", response=list[FAQBrief])
def list_faqs(request):
    authorize(request, "startpage.view_faq")
    return FAQ.objects.all().order_by("question")


@router.post("/faqs", response=FAQOut)
def create_faq(request, payload: FAQIn):
    authorize(request, "startpage.add_faq")
    faq = FAQ(**payload.dict())
    faq.full_clean()
    faq.save()
    return faq


@router.get("/faqs/{faq_id}", response=FAQOut)
def retrieve_faq(request, faq_id: int):
    authorize(request, "startpage.view_faq")
    return get_object_or_404(FAQ, pk=faq_id)


@router.put("/faqs/{faq_id}", response=FAQOut)
def update_faq(request, faq_id: int, payload: FAQIn):
    authorize(request, "startpage.change_faq")
    faq = get_object_or_404(FAQ, pk=faq_id)
    data = payload.dict()
    set_scalar_fields(faq, data, list(data.keys()))
    faq.full_clean()
    faq.save()
    return faq


@router.delete("/faqs/{faq_id}")
def delete_faq(request, faq_id: int):
    authorize(request, "startpage.delete_faq")
    faq = get_object_or_404(FAQ, pk=faq_id)
    faq.delete()
    return {"success": True}


# --- links ----------------------------------------------------------------


@router.get("/links", response=list[LinkBrief])
def list_links(request):
    authorize(request, "startpage.view_link")
    return Link.objects.all().order_by("title")


@router.post("/links", response=LinkOut)
def create_link(request, payload: LinkIn):
    authorize(request, "startpage.add_link")
    link = Link(**payload.dict())
    link.full_clean()
    link.save()
    return link


@router.get("/links/{link_id}", response=LinkOut)
def retrieve_link(request, link_id: int):
    authorize(request, "startpage.view_link")
    return get_object_or_404(Link, pk=link_id)


@router.put("/links/{link_id}", response=LinkOut)
def update_link(request, link_id: int, payload: LinkIn):
    authorize(request, "startpage.change_link")
    link = get_object_or_404(Link, pk=link_id)
    data = payload.dict()
    set_scalar_fields(link, data, list(data.keys()))
    link.full_clean()
    link.save()
    return link


@router.post("/links/{link_id}/icon", response=LinkOut)
def upload_link_icon(request, link_id: int, icon: UploadedFile = File(...)):
    """Set a link's icon, honoring the field's 5 MiB / image content-type limit."""
    authorize(request, "startpage.change_link")
    link = get_object_or_404(Link, pk=link_id)
    _validate_upload(icon, 5, content_types=["image/jpeg", "image/png", "image/gif"])
    link.icon = icon
    link.save()
    return link


@router.delete("/links/{link_id}")
def delete_link(request, link_id: int):
    authorize(request, "startpage.delete_link")
    link = get_object_or_404(Link, pk=link_id)
    link.delete()
    return {"success": True}


# --- images ---------------------------------------------------------------


@router.get("/images", response=list[ImageOut])
def list_images(request):
    authorize(request, "startpage.view_image")
    return Image.objects.all().order_by("id")


@router.post("/images", response=ImageOut)
def create_image(request, post_id: int = Form(...), f: UploadedFile = File(...)):
    """Attach an image file to a post, honoring the field's 10 MiB limit."""
    authorize(request, "startpage.add_image")
    post = get_object_or_404(Post, pk=post_id)
    _validate_upload(f, 10)
    return Image.objects.create(post=post, f=f)


@router.get("/images/{image_id}", response=ImageOut)
def retrieve_image(request, image_id: int):
    authorize(request, "startpage.view_image")
    return get_object_or_404(Image, pk=image_id)


@router.post("/images/{image_id}/file", response=ImageOut)
def replace_image_file(request, image_id: int, f: UploadedFile = File(...)):
    """Replace an image's file, honoring the field's 10 MiB limit.

    Exposed as ``POST`` (not ``PUT``) because ninja's ``PUT`` multipart handling
    needs an extra middleware that is not enabled in this project.
    """
    authorize(request, "startpage.change_image")
    image = get_object_or_404(Image, pk=image_id)
    _validate_upload(f, 10)
    image.f = f
    image.save()
    return image


@router.delete("/images/{image_id}")
def delete_image(request, image_id: int):
    authorize(request, "startpage.delete_image")
    image = get_object_or_404(Image, pk=image_id)
    image.delete()
    return {"success": True}


# --- members on posts -----------------------------------------------------


@router.get("/member-on-posts", response=list[MemberOnPostBrief])
def list_member_on_posts(request):
    authorize(request, "startpage.view_memberonpost")
    return MemberOnPost.objects.all().order_by("id")


@router.post("/member-on-posts", response=MemberOnPostOut)
def create_member_on_post(request, payload: MemberOnPostIn):
    authorize(request, "startpage.add_memberonpost")
    data = payload.dict()
    member_ids = data.pop("member_ids")
    member_on_post = MemberOnPost(**data)
    member_on_post.full_clean()
    member_on_post.save()
    member_on_post.members.set(member_ids)
    return member_on_post


@router.get("/member-on-posts/{mop_id}", response=MemberOnPostOut)
def retrieve_member_on_post(request, mop_id: int):
    authorize(request, "startpage.view_memberonpost")
    return get_object_or_404(MemberOnPost, pk=mop_id)


@router.put("/member-on-posts/{mop_id}", response=MemberOnPostOut)
def update_member_on_post(request, mop_id: int, payload: MemberOnPostIn):
    authorize(request, "startpage.change_memberonpost")
    member_on_post = get_object_or_404(MemberOnPost, pk=mop_id)
    data = payload.dict()
    member_ids = data.pop("member_ids")
    set_scalar_fields(member_on_post, data, list(data.keys()))
    member_on_post.full_clean()
    member_on_post.save()
    member_on_post.members.set(member_ids)
    return member_on_post


@router.delete("/member-on-posts/{mop_id}")
def delete_member_on_post(request, mop_id: int):
    authorize(request, "startpage.delete_memberonpost")
    member_on_post = get_object_or_404(MemberOnPost, pk=mop_id)
    member_on_post.delete()
    return {"success": True}


# --- public read API ------------------------------------------------------
#
# Unauthenticated (``auth=None``) endpoints mirroring the public website views
# in ``startpage/views.py`` so the single-page frontend can render the entire
# public site from the API. Each returns exactly the data its corresponding
# template needs — hidden groups and member contact data never leak here.


@router.get("/public/site", auth=None, response=PublicSiteOut)
def public_site(request):
    """Which section this deployment belongs to (``settings.SEKTION*``).

    The public site and the Kompass chrome both carry the section's name, and
    the imprint its postal details; none of that is section-independent, so it
    is served from the deployment's configuration rather than built into the
    frontend.
    """
    return {
        "name": settings.SEKTION,
        "display_name": f"JDAV {settings.SEKTION}",
        "dav_section": settings.SEKTION_DAV,
        "street": settings.SEKTION_STREET,
        "town": settings.SEKTION_TOWN,
        "telephone": settings.SEKTION_TELEPHONE,
        "telefax": settings.SEKTION_TELEFAX,
        "contact_mail": settings.SEKTION_CONTACT_MAIL,
        "board_mail": settings.SEKTION_BOARD_MAIL,
        "responsible_mail": settings.RESPONSIBLE_MAIL,
        "latitude": settings.SEKTION_LATITUDE,
        "longitude": settings.SEKTION_LONGITUDE,
    }


@router.get("/public/navigation", auth=None, response=NavigationOut)
def public_navigation(request):
    """Navigation context injected on every public page (``views.render``)."""
    return {
        "sections": Section.objects.all(),
        "groups": Group.objects.filter(show_website=True).order_by("name"),
        "root_section": Section.objects.filter(urlname=settings.ROOT_SECTION).first(),
    }


@router.get("/public/index", auth=None, response=IndexOut)
def public_index(request):
    """Landing-page content: recent news posts and reports (``views.index``).

    Bounded: the landing page leads with one story, lists a few more and shows a
    short strip of reports — the full archives live behind /aktuelles and
    /berichte. It previously returned *every* post in both sections, so the page
    grew without limit as the section published.
    """
    posts = Post.objects.prefetch_related("image_set")
    return {
        "recent_posts": posts.filter(section__urlname=settings.RECENT_SECTION).order_by("-date")[
            :5
        ],
        "reports": posts.filter(section__urlname=settings.REPORTS_SECTION).order_by("-date")[:4],
    }


@router.get("/public/aktuelles", auth=None, response=SectionPostsOut)
def public_aktuelles(request):
    """News section with all its posts (``views.aktuelles``)."""
    section = get_object_or_404(Section, urlname=settings.RECENT_SECTION)
    return {"section": section, "posts": Post.objects.filter(section=section)}


@router.get("/public/berichte", auth=None, response=SectionPostsOut)
def public_berichte(request):
    """Reports section with all its posts (``views.berichte``)."""
    section = get_object_or_404(Section, urlname=settings.REPORTS_SECTION)
    return {"section": section, "posts": Post.objects.filter(section=section)}


@router.get("/public/faqs", auth=None, response=list[FAQOut])
def public_faqs(request):
    """Frequently asked questions shown on the Gruppen FAQ page (``views.faq``)."""
    return FAQ.objects.all()


@router.get("/public/groups", auth=None, response=list[PublicGroupBrief])
def public_groups(request):
    """Groups listed on the public Gruppen page (``show_website`` only)."""
    return Group.objects.filter(show_website=True).order_by("name")


@router.get("/public/groups/{group_name}", auth=None, response=PublicGroupDetail)
def public_group_detail(request, group_name: str):
    """A single public group with its youth leaders (``views.gruppe_detail``).

    Groups not flagged ``show_website`` are hidden (404), exactly like the view.
    """
    group = get_object_or_404(Group, name=group_name)
    if not group.show_website:
        raise Http404("Group not found.")
    return group


@router.get("/public/sections", auth=None, response=list[SectionBrief])
def public_sections(request):
    """All website sections (public navigation source, ``views.render``)."""
    return Section.objects.all().order_by("title")


@router.get("/public/sections/{section_name}", auth=None, response=SectionOut)
def public_section_detail(request, section_name: str):
    """A single section's rendered content by urlname (``views.section``)."""
    return get_object_or_404(Section, urlname=section_name)


@router.get(
    "/public/sections/{section_name}/posts/{post_name}",
    auth=None,
    response=PublicPostDetail,
)
def public_post_detail(request, section_name: str, post_name: str):
    """A single post within a section, with its credited people (``views.post``)."""
    section = get_object_or_404(Section, urlname=section_name)
    return get_object_or_404(Post, section=section, urlname=post_name)
