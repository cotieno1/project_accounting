from django.core.management.base import BaseCommand
from django.test import RequestFactory

from accounts.emails import build_password_set_url, send_onboarding_email
from accounts.models import Organization
from buildwatch.models import BidWorkspace, SubcontractArrangement, TenderListing
from buildwatch.subcontract_orgs import (
    ensure_contractor_organisation,
    ensure_subcontractor_employee,
    link_arrangement_to_contractor,
)


class Command(BaseCommand):
    help = (
        "Ensure LANBase contractor ID exists, onboard Otieno as LANBase employee, "
        "and link LANBase as Pioneer Isiolo sub-contractor for project lifetime."
    )

    def add_arguments(self, parser):
        parser.add_argument("--listing-id", type=int, default=1)
        parser.add_argument("--email", default="")
        parser.add_argument("--send-email", action="store_true")
        parser.add_argument(
            "--set-password",
            default="",
            help="Optional plaintext password for lanbase.otieno (demo / handover).",
        )

    def handle(self, *args, **options):
        listing = TenderListing.objects.filter(pk=options["listing_id"]).select_related(
            "event"
        ).first()
        if not listing:
            self.stderr.write(self.style.ERROR("Tender listing not found"))
            return

        arrangement = (
            SubcontractArrangement.objects.filter(tender=listing)
            .exclude(status=SubcontractArrangement.CANCELLED)
            .order_by("pk")
            .first()
        )
        if not arrangement:
            self.stderr.write(self.style.ERROR("No active subcontract arrangement on this tender"))
            return

        email = (options["email"] or arrangement.sub_email or "").strip()
        org, org_created = ensure_contractor_organisation(
            company_name=arrangement.sub_company_name or "LANBase System Technologies",
            email=email,
            phone=arrangement.sub_phone or "",
            org_code="LANBASE",
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{'Created' if org_created else 'Found'} contractor ID {org.org_code} "
                f"({org.short_name} / {org.name})"
            )
        )

        ua, ua_created = ensure_subcontractor_employee(
            organization=org,
            email=email,
            contact_name=arrangement.sub_contact_name or "Charles Otieno",
            phone=arrangement.sub_phone or "",
            staff_no="LB-OTIENO-01",
            username="lanbase.otieno",
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{'Created' if ua_created else 'Found'} employee {ua.staff_no} "
                f"login={(ua.user.username if ua.user_id else 'none')} email={ua.email}"
            )
        )

        link_arrangement_to_contractor(arrangement, org)
        self.stdout.write(
            self.style.SUCCESS(
                f"Linked arrangement #{arrangement.pk} -> sub_organisation={org.org_code} "
                f"packages={arrangement.package_codes}"
            )
        )

        pioneer = Organization.objects.filter(org_code="PIONEER").first()
        if pioneer:
            ws = BidWorkspace.objects.filter(tender=listing, organisation=pioneer).first()
            if ws and ws.planned_subcontractor_count is None:
                ws.planned_subcontractor_count = 1
                ws.save(update_fields=["planned_subcontractor_count"])

        my_subs = "/tenders/my-subcontracts/"
        self.stdout.write("Portal: /tenders/subcontract/portal/<token>/")
        self.stdout.write(f"My subcontracts: {my_subs}")

        factory = RequestFactory()
        request = factory.get("/")
        request.META["HTTP_HOST"] = "projectaccounting-production.up.railway.app"
        request.META["wsgi.url_scheme"] = "https"

        if options["set_password"]:
            if not ua.user_id:
                self.stderr.write("No Django user on account - cannot set password")
            else:
                ua.user.set_password(options["set_password"])
                ua.user.save()
                ua.must_change_password = False
                ua.save(update_fields=["must_change_password"])
                self.stdout.write(self.style.SUCCESS(
                    f"Password set for login user '{ua.user.username}'. "
                    f"Sign in then open {my_subs}."
                ))
        else:
            try:
                url = build_password_set_url(ua.user, request)
                self.stdout.write(f"Onboarding set-password URL: {url}")
            except Exception as exc:
                self.stdout.write(f"Could not build set-password URL: {exc}")

        if options["send_email"]:
            ok, err = send_onboarding_email(ua, request=request)
            if ok:
                self.stdout.write(self.style.SUCCESS(f"Onboarding email sent to {ua.email}"))
            else:
                self.stderr.write(self.style.ERROR(f"Email failed: {err}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Pioneer bid page should list {org.short_name} as Isiolo sub. "
                f"Ref={listing.event.ref}"
            )
        )
