"""Load an awarded tender's priced BOQ into the execution BOM without duplication."""

from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Count, Sum

from accounts.models import BOMHeader, BOMItem


def awarded_boq_source(task):
    """
    Return the tender/workspace/categories linked through task.infra_profile.

    This deliberately uses the Close Tender execution task (for example
    SK_004_2025). It does not depend on, or copy from, the separate PT-* Fin Ops
    task.
    """
    if not task:
        return None

    from buildwatch.models import (
        BidWorkspace,
        PublicTenderProfile,
        TenderBoqPackage,
        TenderListing,
    )

    try:
        infra = task.infra_profile
    except ObjectDoesNotExist:
        infra = None
    if infra is None:
        return None

    listing = (
        TenderListing.objects.filter(event__project=infra)
        .select_related("event")
        .order_by("-created_at", "-pk")
        .first()
    )
    if listing is None or not listing.boq_packages.exists():
        return None

    workspaces = BidWorkspace.objects.filter(tender=listing).select_related(
        "organisation", "submission"
    )
    workspace = workspaces.filter(submission__is_awarded=True).order_by("-id").first()
    if workspace is None:
        profile = (
            PublicTenderProfile.objects.filter(tender=listing)
            .select_related("contractor_org")
            .order_by("-created_at")
            .first()
        )
        if profile and profile.contractor_org_id:
            workspace = (
                workspaces.filter(organisation_id=profile.contractor_org_id)
                .order_by("-id")
                .first()
            )
    if workspace is None:
        submitted = workspaces.filter(status=BidWorkspace.SUBMITTED)
        if submitted.count() == 1:
            workspace = submitted.first()
    if workspace is None and workspaces.count() == 1:
        # Supports old/seeded awards whose evaluation status was not backfilled.
        workspace = workspaces.first()

    packages = TenderBoqPackage.objects.filter(tender=listing).annotate(
        line_count=Count("lines")
    )
    selected_codes = set(workspace.selected_codes()) if workspace else set()
    if selected_codes:
        packages = packages.filter(code__in=selected_codes)

    price_totals = {}
    if workspace:
        price_totals = {
            row["package_code"]: row["total"] or Decimal("0")
            for row in workspace.bill_prices.values("package_code")
            .annotate(total=Sum("amount"))
        }

    categories = []
    for package in packages.order_by("sort_order", "code"):
        categories.append(
            {
                "code": package.code,
                "title": package.title,
                "line_count": package.line_count,
                "priced_total": price_totals.get(package.code, Decimal("0")),
            }
        )

    if not categories:
        return None

    return {
        "listing": listing,
        "tender_ref": listing.event.ref,
        "tender_title": listing.event.description,
        "workspace": workspace,
        "contractor": workspace.organisation if workspace else None,
        "categories": categories,
        "category_codes": [row["code"] for row in categories],
    }


@transaction.atomic
def load_awarded_boq_categories(task, package_codes):
    """
    Idempotently load selected measured BOQ categories into one draft BOM.

    Returns ``(header, created_count, skipped_count)``. Existing source lines are
    skipped using their stable TenderBoqLine primary keys.
    """
    from buildwatch.models import TenderBoqLine, WorkspaceBillPrice

    source = awarded_boq_source(task)
    if source is None:
        raise ValueError("No awarded tender BOQ is linked to this project task.")

    allowed = set(source["category_codes"])
    selected = [str(code).strip() for code in package_codes if str(code).strip()]
    selected = list(dict.fromkeys(code for code in selected if code in allowed))
    if not selected:
        raise ValueError("Select at least one awarded BOQ item category.")

    header, _ = BOMHeader.objects.get_or_create(
        task=task,
        defaults={"status": BOMHeader.STATUS_DRAFT},
    )
    if header.items_locked or header.status != BOMHeader.STATUS_DRAFT:
        raise ValueError(
            "BOM %s is locked or submitted; awarded categories cannot be reloaded."
            % (header.bom_id or header.pk)
        )

    listing = source["listing"]
    lines = list(
        TenderBoqLine.objects.filter(
            package__tender=listing,
            package__code__in=selected,
        )
        .select_related("package")
        .order_by("package__sort_order", "package__code", "sort_order", "bill_ref")
    )
    if not lines:
        raise ValueError("The selected categories contain no measured BOQ lines.")

    workspace = source["workspace"]
    prices = {}
    if workspace:
        for price in WorkspaceBillPrice.objects.filter(
            workspace=workspace,
            package_code__in=selected,
        ):
            prices[(price.package_code, price.bill_ref)] = price.unit_rate

    existing_keys = set(
        header.items.exclude(source_line_key="").values_list("source_line_key", flat=True)
    )
    to_create = []
    skipped = 0
    tender_ref = source["tender_ref"]
    for line in lines:
        source_key = "tender-line:%s" % line.pk
        if source_key in existing_keys:
            skipped += 1
            continue
        to_create.append(
            BOMItem(
                header=header,
                pillar_id=2,
                description=line.description,
                qty=line.quantity,
                uom=line.unit or "No",
                unit_price=prices.get((line.package.code, line.bill_ref), Decimal("0")),
                source_tender_ref=tender_ref,
                source_package_code=line.package.code,
                source_bill_ref=line.bill_ref,
                source_line_key=source_key,
            )
        )

    BOMItem.objects.bulk_create(to_create, batch_size=500, ignore_conflicts=True)
    return header, len(to_create), skipped
