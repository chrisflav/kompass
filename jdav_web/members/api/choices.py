"""Choice options shared by the members API's ``/enums`` routes.

The SPA renders every members-app ``<select>`` from these lists instead of
mirroring ``members.models`` choice fields in TypeScript.
"""

from members.models import ActivityCategory
from members.models import Freizeit
from members.models import Group
from members.models import LJPProposal
from members.models import Member

# Group/Freizeit/ActivityCategory/LJPProposal choice fields whose
# ``{value, label, default}`` options are surfaced by ``GET /activities/enums``
# so the SPA can render labelled selects for them.
ACTIVITY_CHOICE_FIELDS = (
    (Group, "weekday"),
    (Freizeit, "difficulty"),
    (Freizeit, "tour_type"),
    (Freizeit, "tour_approach"),
    (ActivityCategory, "ljp_category"),
    (LJPProposal, "category"),
    (LJPProposal, "goal"),
    (LJPProposal, "not_bw_reason"),
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


def activity_choice_options():
    """``{field: [{"value": …, "label": …, "default": …}, …]}`` per choice field."""
    return {name: _options(model._meta.get_field(name)) for model, name in ACTIVITY_CHOICE_FIELDS}


def member_choice_options():
    """``{field: [{"value": …, "label": …, "default": …}, …]}`` for every
    choice field of the ``Member`` model (currently just ``gender``)."""
    result = {}
    for field in Member._meta.get_fields():
        if getattr(field, "choices", None):
            result[field.name] = _options(field)
    return result


def gender_choice_options():
    """``{"gender": [{"value": …, "label": …, "default": …}, …]}``.

    Served without authentication too: the waiting-list, registration and echo
    forms are public, and the gender select is model metadata, not data about
    anyone.
    """
    return {"gender": member_choice_options()["gender"]}
