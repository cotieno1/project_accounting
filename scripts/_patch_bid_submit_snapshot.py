from pathlib import Path

# --- Enhance BidWorkspace.submit to snapshot ---
mp = Path("buildwatch/models.py")
mt = mp.read_text(encoding="utf-8")
old_submit_tail = """        submission = Submission.objects.create(
            event=self.tender.event,
            submitter_org=self.organisation,
            submitted_by=submitted_by,
            submitted_at=timezone.now(),
            tender_total=self.total_bid_amount,
        )
        self.submission     = submission
        self.status         = self.SUBMITTED
        self.submitted_at   = timezone.now()
        self.save()
"""
new_submit_tail = """        # Refresh total from priced lines
        from django.db.models import Sum
        total = (
            self.bill_prices.aggregate(s=Sum("amount")).get("s")
            or Decimal("0")
        )
        self.total_bid_amount = total
        self.save(update_fields=["total_bid_amount"])

        submission = Submission.objects.create(
            event=self.tender.event,
            submitter_org=self.organisation,
            submitted_by=submitted_by,
            submitted_at=timezone.now(),
            tender_total=self.total_bid_amount,
        )

        # Snapshot BOQ prices for employer evaluation
        for bp in self.bill_prices.all():
            SubmissionBillPrice.objects.create(
                submission=submission,
                bill_ref=bp.bill_ref[:20],
                description=(bp.description or "")[:255],
                qs_estimate=Decimal("0"),
                submitted_amount=bp.amount,
            )

        # Snapshot self-assessment / certificate checklist
        for sc in self.self_checks.all():
            result = MandatoryCheck.PASS if sc.self_result == SelfAssessmentCheck.PASS else MandatoryCheck.FAIL
            doc_name = ""
            if sc.document:
                doc_name = Path(sc.document.name).name[:200]
            MandatoryCheck.objects.create(
                submission=submission,
                requirement=sc.requirement,
                mr_ref=sc.mr_ref,
                description=(sc.description or "")[:500],
                result=result,
                notes=sc.notes or "",
                document_ref=doc_name,
                checked_by=submitted_by,
            )

        self.submission     = submission
        self.status         = self.SUBMITTED
        self.submitted_at   = timezone.now()
        self.save()
"""
# Need Path import in models? Use string slice instead of Path
new_submit_tail = new_submit_tail.replace(
    "doc_name = Path(sc.document.name).name[:200]",
    "doc_name = sc.document.name.rsplit('/', 1)[-1][:200]",
)

if "Snapshot BOQ prices for employer evaluation" in mt:
    print("submit snapshot already present")
else:
    if old_submit_tail not in mt:
        raise SystemExit("submit block not found")
    mp.write_text(mt.replace(old_submit_tail, new_submit_tail, 1), encoding="utf-8")
    print("submit snapshot added")

# Ensure SelfAssessmentCheck is in scope in submit - it's in same models file so OK
# MandatoryCheck and SubmissionBillPrice also same file OK

compile(mp.read_text(encoding="utf-8"), "models.py", "exec")
print("models compile ok")
