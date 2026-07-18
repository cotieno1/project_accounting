from pathlib import Path

p = Path("buildwatch/models.py")
t = p.read_text(encoding="utf-8")
if "boq_input_mode" in t:
    print("already has boq_input_mode")
else:
    needle = """    boq_document    = models.FileField(upload_to='tenders/boq/%Y/%m/',
                          null=True, blank=True,
                          help_text='Structured BOQ PDF or XLSX')"""
    insert = """    # A = curated hardwired seed; B = adapter parse from RFQ/BOQ PDF (same bid form)
    BOQ_HARDWIRED = 'HARDWIRED'
    BOQ_PDF_AUTO  = 'PDF_AUTO'
    BOQ_INPUT_MODE_CHOICES = [
        (BOQ_HARDWIRED, 'A - Hardwired BOQ (curated seed)'),
        (BOQ_PDF_AUTO,  'B - Automated from RFQ/BOQ PDF'),
    ]
    boq_input_mode  = models.CharField(
        max_length=20,
        choices=BOQ_INPUT_MODE_CHOICES,
        default=BOQ_HARDWIRED,
        help_text='Which BOQ source feeds the bid workspace form',
    )

    boq_document    = models.FileField(upload_to='tenders/boq/%Y/%m/',
                          null=True, blank=True,
                          help_text='Structured BOQ PDF or XLSX')"""
    if needle not in t:
        raise SystemExit("needle missing")
    p.write_text(t.replace(needle, insert), encoding="utf-8")
    print("model patched")
