"""Termin choice options, shared by the authenticated and the public ``/enums``.

The SPA renders every Termin ``<select>`` from these lists instead of mirroring
``ludwigsburgalpin.models`` in TypeScript. The public submission form needs the
same options without a bearer token, so both routers serve one helper rather
than each building the payload itself.
"""

from ludwigsburgalpin.models import Termin

# Termin choice fields whose ``{value, label, default}`` options are surfaced
# by ``GET /enums`` so the SPA can render labelled selects for them.
TERMIN_CHOICE_FIELDS = (
    "group",
    "category",
    "condition",
    "technik",
    "saison",
    "eventart",
    "klassifizierung",
)


def _options(field):
    """The ``{value, label, default}`` options of one choice field."""
    default = field.get_default() if field.has_default() else None
    options = [
        {"value": value, "label": str(label), "default": value == default}
        for value, label in field.choices
    ]
    # A default outside its own choices would mark nothing, and the SPA would
    # then preselect the first option instead — a plausible-looking form rather
    # than a visible failure. Say so here instead of shipping the wrong one.
    assert default is None or any(o["default"] for o in options), (
        f"{field.name} defaults to {default!r}, which is not one of its choices"
    )
    return options


def termin_choice_options():
    """``{field: [{"value": …, "label": …, "default": …}, …]}`` per choice field."""
    return {name: _options(Termin._meta.get_field(name)) for name in TERMIN_CHOICE_FIELDS}
