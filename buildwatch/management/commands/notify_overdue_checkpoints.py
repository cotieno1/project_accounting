"""Raise missed-step alerts for overdue compliance checkpoints.

Finds checkpoints past their due date that are not yet approved/NA, emails the
responsible person and the procuring entity, and records an AuditLedger entry.
Idempotent per run window: re-notifies at most once every --cooldown-hours.

Run on a schedule (cron / Railway deploy hook):
    python manage.py notify_overdue_checkpoints
"""
from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from buildwatch.models import AuditLedger, ComplianceCheckpoint


class Command(BaseCommand):
    help = "Email responsible people about overdue (missed) compliance checkpoints."

    def add_arguments(self, parser):
        parser.add_argument("--cooldown-hours", type=int, default=24,
                            help="Minimum hours between repeat alerts for the same checkpoint.")
        parser.add_argument("--dry-run", action="store_true",
                            help="Report what would be sent without emailing.")

    def handle(self, *args, **opts):
        cooldown = int(opts.get("cooldown_hours") or 24)
        dry = bool(opts.get("dry_run"))
        now = timezone.now()
        today = now.date()
        cutoff = now - timedelta(hours=cooldown)

        due = (
            ComplianceCheckpoint.objects
            .filter(due_date__lt=today)
            .exclude(status__in=[ComplianceCheckpoint.STATUS_APPROVED,
                                 ComplianceCheckpoint.STATUS_NA])
            .select_related("tender__event", "tender__event__project__owner_org",
                            "responsible_user")
        )

        sent = 0
        skipped = 0
        for cp in due:
            if cp.overdue_notified_at and cp.overdue_notified_at > cutoff:
                skipped += 1
                continue

            listing = cp.tender
            owner_org = getattr(getattr(listing.event, "project", None), "owner_org", None)
            recipients = []
            if cp.responsible_user and cp.responsible_user.email:
                recipients.append(cp.responsible_user.email)
            if owner_org and getattr(owner_org, "email", ""):
                recipients.append(owner_org.email)
            recipients = list(dict.fromkeys([r for r in recipients if r]))

            self.stdout.write(
                "OVERDUE %s | %s | due %s | -> %s"
                % (listing.event.ref, cp.title[:50], cp.due_date, ", ".join(recipients) or "(no email)")
            )

            if dry:
                continue

            if recipients:
                try:
                    from accounts.emails import send_system_email

                    send_system_email(
                        subject="MISSED STEP: %s (%s)" % (cp.title, listing.event.ref),
                        to=recipients,
                        text_body=(
                            "Compliance checkpoint '%s' (%s) on tender %s is OVERDUE.\n"
                            "Due date: %s. Current status: %s.\n\n"
                            "Please complete and submit for sign-off."
                            % (cp.title, cp.get_category_display(), listing.event.ref,
                               cp.due_date, cp.get_status_display())
                        ),
                    )
                except Exception as exc:
                    self.stdout.write(self.style.WARNING("  ! email failed: %s" % exc))

            if cp.responsible_user_id:
                try:
                    AuditLedger.objects.create(
                        project=getattr(listing.event, "project", None),
                        user=cp.responsible_user,
                        action="COMPLIANCE_OVERDUE_ALERT",
                        model_name="ComplianceCheckpoint",
                        object_id=str(cp.pk),
                        detail={"code": cp.code, "title": cp.title, "due_date": str(cp.due_date)},
                        professional_reg="",
                    )
                except Exception:
                    pass

            cp.overdue_notified_at = now
            cp.save(update_fields=["overdue_notified_at"])
            sent += 1

        self.stdout.write(self.style.SUCCESS(
            "Overdue alerts: %d sent, %d within cooldown." % (sent, skipped)
        ))
