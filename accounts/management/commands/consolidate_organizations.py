"""Remove malformed duplicate organizations and keep PIONEER as company 1."""
import re

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Organization, UserAccount

CANONICAL_ORG_CODE = "PIONEER"
JUNK_ORG_CODE_PATTERN = re.compile(r"^[\[\]'\"\s]+|[\[\]'\"\s]+$")


def _normalize_org_code(raw):
    code = (raw or "").strip()
    if code.startswith("[") and code.endswith("]"):
        inner = code[1:-1].strip().strip("'\"")
        if inner:
            code = inner
    return code.strip("[]'\" ")


class Command(BaseCommand):
    help = (
        "Remove junk duplicate Organization rows, keep canonical PIONEER, "
        "and ensure default tenant is set."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default="cotieno",
            help="Login username to assign to PIONEER when a UserAccount exists.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show actions without writing changes.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        username = (options["username"] or "").strip()
        User = get_user_model()

        canonical = Organization.objects.filter(org_code=CANONICAL_ORG_CODE).first()
        if not canonical:
            self.stdout.write(
                self.style.ERROR(
                    f"Canonical org {CANONICAL_ORG_CODE} missing. Run migrate / ensure_bootstrap first."
                )
            )
            return

        junk_orgs = []
        for org in Organization.objects.exclude(org_code=CANONICAL_ORG_CODE):
            code = org.org_code or ""
            normalized = _normalize_org_code(code)
            if normalized == CANONICAL_ORG_CODE or JUNK_ORG_CODE_PATTERN.search(code):
                junk_orgs.append(org)

        self.stdout.write(f"Canonical company: {canonical.org_code} | {canonical.name}")
        self.stdout.write(f"Junk duplicates to remove: {len(junk_orgs)}")
        for org in junk_orgs:
            linked = UserAccount.objects.filter(organization=org).count()
            self.stdout.write(f"  - {org.org_code!r} | {org.name!r} | users={linked}")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run - no changes made."))
            return

        with transaction.atomic():
            for org in junk_orgs:
                moved = UserAccount.objects.filter(organization=org).update(
                    organization=canonical
                )
                if moved:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Reassigned {moved} user(s) from {org.org_code!r} to {CANONICAL_ORG_CODE}."
                        )
                    )
                deleted_code = org.org_code
                org.delete()
                self.stdout.write(self.style.SUCCESS(f"Deleted junk org {deleted_code!r}."))

            if not canonical.is_default:
                Organization.objects.exclude(pk=canonical.pk).update(is_default=False)
                canonical.is_default = True
                canonical.save(update_fields=["is_default"])
                self.stdout.write(self.style.SUCCESS("Marked PIONEER as default tenant."))

            user = User.objects.filter(username=username).first()
            if user:
                ua = UserAccount.objects.filter(user=user).first()
                if ua and ua.organization_id != CANONICAL_ORG_CODE:
                    ua.organization = canonical
                    ua.save(update_fields=["organization"])
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Linked {username} UserAccount to {CANONICAL_ORG_CODE}."
                        )
                    )
                elif not ua:
                    self.stdout.write(
                        self.style.WARNING(
                            f"{username} has no UserAccount row - login uses default org "
                            f"({CANONICAL_ORG_CODE}) via platform fallback."
                        )
                    )

        remaining = list(
            Organization.objects.order_by("org_code").values_list("org_code", "name", "is_default")
        )
        self.stdout.write(f"Remaining organizations: {remaining}")
