"""Ledger (Konto) CRUD routes for the finance API.

``Ledger`` is a plain model registered with a plain :class:`admin.ModelAdmin`
(``LedgerAdmin``), so it carries the default Django model permissions rather than
the custom ``CommonModel`` object-level rules. Each operation is therefore gated
globally via :func:`contrib.api.perms.authorize` against the matching default
permission (``finance.view_ledger`` / ``add_ledger`` / ``change_ledger`` /
``delete_ledger``), reproducing exactly what the admin enforces.

The list/brief representation ``LedgerBrief`` already exists (nested inside
``TransactionOut``); the schemas here are named distinctly to avoid colliding
with it in the shared OpenAPI component registry.
"""

from contrib.api.perms import authorize
from django.shortcuts import get_object_or_404
from finance.models import Ledger
from ninja import ModelSchema
from ninja import Router
from ninja import Schema

router = Router()


class LedgerListOut(ModelSchema):
    # Declared explicitly so the response contract types it as a required
    # non-null int (ModelSchema would otherwise mark the AutoField optional).
    id: int

    class Meta:
        model = Ledger
        fields = ["name"]


class LedgerDetailOut(ModelSchema):
    id: int

    class Meta:
        model = Ledger
        fields = ["name"]


class LedgerCreate(Schema):
    name: str


class LedgerUpdate(Schema):
    """Editable ledger fields; PATCH semantics (only supplied fields applied)."""

    name: str | None = None


@router.get("/", response=list[LedgerListOut])
def list_ledgers(request):
    """List all ledgers (default ``finance.view_ledger`` perm, checked globally)."""
    authorize(request, "finance.view_ledger")
    return Ledger.objects.all().order_by("name")


@router.post("/", response=LedgerDetailOut)
def create_ledger(request, payload: LedgerCreate):
    """Create a ledger (default ``finance.add_ledger`` perm)."""
    authorize(request, "finance.add_ledger")
    return Ledger.objects.create(name=payload.name)


@router.get("/{ledger_id}", response=LedgerDetailOut)
def retrieve_ledger(request, ledger_id: int):
    """Ledger detail (default ``finance.view_ledger`` perm)."""
    authorize(request, "finance.view_ledger")
    return get_object_or_404(Ledger, pk=ledger_id)


@router.patch("/{ledger_id}", response=LedgerDetailOut)
def update_ledger(request, ledger_id: int, payload: LedgerUpdate):
    """Update a ledger (default ``finance.change_ledger`` perm)."""
    authorize(request, "finance.change_ledger")
    ledger = get_object_or_404(Ledger, pk=ledger_id)
    for field, value in payload.dict(exclude_unset=True).items():
        setattr(ledger, field, value)
    ledger.save()
    return ledger


@router.delete("/{ledger_id}", response={204: None})
def delete_ledger(request, ledger_id: int):
    """Delete a ledger (default ``finance.delete_ledger`` perm)."""
    authorize(request, "finance.delete_ledger")
    ledger = get_object_or_404(Ledger, pk=ledger_id)
    ledger.delete()
    return 204, None
