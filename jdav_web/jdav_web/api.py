"""Root NinjaAPI instance for the Kompass REST API.

Mounted at ``/api/`` (see ``jdav_web/urls.py``). App routers are attached here.
The OpenAPI schema is served at ``/api/openapi.json`` and interactive docs at
``/api/docs`` — this schema is the contract the TypeScript frontend is
generated from.
"""

from contrib.api.auth import OAuth2Bearer
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from ninja import NinjaAPI
from ninja.throttling import AnonRateThrottle
from ninja.throttling import AuthRateThrottle

api = NinjaAPI(
    title="Kompass API",
    version="1.0.0",
    description="REST API for the Kompass administration platform.",
    # Bearer tokens carry no ambient authority (no cookies), so CSRF does not
    # apply. Session-based browser auth can be added later behind ninja's
    # django_auth (which auto-enables CSRF) for a same-origin browsable API.
    auth=OAuth2Bearer(),
    # Coarse DoS backstop: per-IP for anonymous (public) requests, per-user for
    # authenticated ones. Rates are configurable (see settings/components/api.py).
    throttle=[
        AnonRateThrottle(settings.API_ANON_THROTTLE_RATE),
        AuthRateThrottle(settings.API_AUTH_THROTTLE_RATE),
    ],
)


@api.exception_handler(PermissionDenied)
def on_permission_denied(request, exc):
    return api.create_response(request, {"detail": str(exc) or "Forbidden"}, status=403)


@api.exception_handler(ValidationError)
def on_validation_error(request, exc):
    # Expose per-field errors (from ``full_clean``'s error_dict) so the SPA can
    # render each message on its own input; ``__all__`` holds non-field errors.
    # ``detail`` (flat list) is kept for generic toast display / back-compat.
    if hasattr(exc, "error_dict"):
        errors = {field: [str(m) for m in msgs] for field, msgs in exc.message_dict.items()}
    else:
        errors = {"__all__": [str(m) for m in exc.messages]}
    return api.create_response(request, {"detail": exc.messages, "errors": errors}, status=422)


@api.get("/ping", auth=None, tags=["meta"])
def ping(request):
    """Unauthenticated liveness probe."""
    return {"status": "ok"}


def _register_routers():
    """Attach app routers. Imported lazily to avoid app-registry import cycles."""
    from finance.api.documents import router as finance_documents_router
    from finance.api.inlines import router as finance_inlines_router
    from finance.api.ledgers import router as finance_ledgers_router
    from finance.api.router import router as finance_router
    from logindata.api.router import router as logindata_router
    from ludwigsburgalpin.api.documents import router as ludwigsburgalpin_documents_router
    from ludwigsburgalpin.api.public import router as ludwigsburgalpin_public_router
    from ludwigsburgalpin.api.router import router as ludwigsburgalpin_router
    from mailer.api.public import router as mailer_public_router
    from mailer.api.router import router as mailer_router
    from material.api.router import router as material_router
    from members.api.documents import router as members_documents_router
    from members.api.inlines_excursion import router as members_inlines_excursion_router
    from members.api.inlines_group import router as members_inlines_group_router
    from members.api.inlines_member import router as members_inlines_router
    from members.api.public import router as members_public_router
    from members.api.router import router as members_router
    from startpage.api.router import router as startpage_router

    # Authenticated (OAuth2 bearer) surfaces.
    api.add_router("/members", members_router, tags=["members"])
    api.add_router("/members/documents", members_documents_router, tags=["members-documents"])
    # Admin-inline related-object CRUD (second/third routers on /members; their
    # routes are all multi-segment/static-prefixed so they don't collide with
    # members_router's terminal /{member_id} route).
    api.add_router("/members", members_inlines_router, tags=["members-inlines"])
    api.add_router("/members", members_inlines_group_router, tags=["members-inlines"])
    api.add_router("/members", members_inlines_excursion_router, tags=["members-inlines"])
    api.add_router("/finance", finance_router, tags=["finance"])
    api.add_router("/finance", finance_inlines_router, tags=["finance"])
    api.add_router("/finance/documents", finance_documents_router, tags=["finance"])
    api.add_router("/finance/ledgers", finance_ledgers_router, tags=["finance"])
    api.add_router("/mailer", mailer_router, tags=["mailer"])
    api.add_router("/material", material_router, tags=["material"])
    api.add_router("/ludwigsburgalpin", ludwigsburgalpin_router, tags=["ludwigsburgalpin"])
    api.add_router(
        "/ludwigsburgalpin/documents",
        ludwigsburgalpin_documents_router,
        tags=["ludwigsburgalpin"],
    )
    api.add_router("/startpage", startpage_router, tags=["startpage"])

    # Public (unauthenticated, secret-key or read-only) surfaces. Every route in
    # these routers sets auth=None itself, so the prefix carries no ambient auth.
    api.add_router("/members/public", members_public_router, tags=["members-public"])
    api.add_router("/mailer/public", mailer_public_router, tags=["mailer", "public"])
    api.add_router("/logindata", logindata_router, tags=["logindata", "public"])
    api.add_router(
        "/ludwigsburgalpin/public",
        ludwigsburgalpin_public_router,
        tags=["ludwigsburgalpin", "public"],
    )


_register_routers()
