from pathlib import Path

path = Path(r"C:\project_accounting\buildwatch\models.py")
text = path.read_text(encoding="utf-8")

old_tail = """    submission          = models.OneToOneField(Submission,
                              on_delete=models.SET_NULL,
                              null=True, blank=True,
                              related_name='workspace')

    class Meta:
        unique_together = [['tender', 'organisation']]
        ordering        = ['-started_at']

    def __str__(self):
        return (f"{self.tender.event.ref} workspace — "
                f"{self.organisation.short_name} [{self.status}]")

    def submit(self, submitted_by):
"""

if "selected_package_codes" not in text:
    if old_tail not in text:
        raise SystemExit("BidWorkspace block not found exactly")
    new_tail = old_tail.replace(
        "related_name='workspace')\n\n    class Meta:",
        "related_name='workspace')\n    selected_package_codes = models.JSONField(\n"
        "        default=list,\n"
        "        blank=True,\n"
        "        help_text='TenderBoqPackage.code values selected for this bid',\n"
        "    )\n\n    class Meta:",
        1,
    ).replace(
        "def submit(self, submitted_by):\n",
        "def selected_codes(self):\n"
        "        codes = self.selected_package_codes or []\n"
        "        return [str(c).strip().upper() for c in codes if str(c).strip()]\n\n"
        "    def submit(self, submitted_by):\n",
        1,
    )
    text = text.replace(old_tail, new_tail, 1)

old_val = '''        if not self.pricing_complete:
            raise ValueError(
                "All BOQ items must be priced before submitting."
            )'''
new_val = '''        if not self.selected_codes():
            raise ValueError(
                "Select at least one BOQ component before submitting."
            )
        if not self.pricing_complete:
            raise ValueError(
                "Price all lines in your selected BOQ components before submitting."
            )'''
if "Select at least one BOQ component" not in text:
    if old_val not in text:
        raise SystemExit("pricing_complete validation not found")
    text = text.replace(old_val, new_val, 1)

insert_marker = "\n\nclass SelfAssessmentCheck(models.Model):"
if "class TenderBoqPackage" not in text:
    package_block = '''

class TenderBoqPackage(models.Model):
    """BOQ component / lot (Electrical, Structured Cabling, CCTV, Solar)."""
    tender      = models.ForeignKey(TenderListing, on_delete=models.CASCADE,
                      related_name='boq_packages')
    code        = models.CharField(max_length=20)
    title       = models.CharField(max_length=120)
    sort_order  = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = [['tender', 'code']]
        ordering = ['sort_order', 'code']

    def __str__(self):
        return f"{self.code} — {self.title}"


class TenderBoqLine(models.Model):
    """Employer-published BOQ line under a package."""
    package     = models.ForeignKey(TenderBoqPackage, on_delete=models.CASCADE,
                      related_name='lines')
    bill_ref    = models.CharField(max_length=20)
    description = models.CharField(max_length=255)
    unit        = models.CharField(max_length=30, blank=True, default='Sum')
    quantity    = models.DecimalField(max_digits=12, decimal_places=3,
                      default=Decimal('1'))
    sort_order  = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = [['package', 'bill_ref']]
        ordering = ['sort_order', 'bill_ref']

    def __str__(self):
        return f"{self.bill_ref} — {self.description[:40]}"


class SelfAssessmentCheck(models.Model):'''
    if insert_marker not in text:
        raise SystemExit("SelfAssessmentCheck marker not found")
    text = text.replace(insert_marker, package_block, 1)

# audit packages + safe getattr
text = text.replace(
    "'total':        str(self.total_bid_amount),\n            },\n            professional_reg=submitted_by.professional_reg_no,",
    "'total':        str(self.total_bid_amount),\n                'packages':     self.selected_codes(),\n            },\n            professional_reg=getattr(submitted_by, 'professional_reg_no', '') or '',",
    1,
)

old_amt = """    amount          = models.DecimalField(max_digits=15, decimal_places=2,
                          default=Decimal('0'))
    # Market intelligence (set from anonymised historical data)"""
new_amt = """    amount          = models.DecimalField(max_digits=15, decimal_places=2,
                          default=Decimal('0'))
    package_code    = models.CharField(max_length=20, blank=True, default='',
                          help_text='TenderBoqPackage.code this line belongs to')
    # Market intelligence (set from anonymised historical data)"""
if "package_code" not in text:
    if old_amt not in text:
        raise SystemExit("WorkspaceBillPrice amount block not found")
    text = text.replace(old_amt, new_amt, 1)

path.write_text(text, encoding="utf-8")
compile(text, "models.py", "exec")
print("patched ok")
