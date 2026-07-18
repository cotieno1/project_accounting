from pathlib import Path
p = Path("buildwatch/models.py")
t = p.read_text(encoding="utf-8")
old = "    amount          = models.DecimalField(max_digits=15, decimal_places=2,\n                          default=Decimal('0'))\n    # Market intelligence (set from anonymised historical data)\n    market_rate_low"
new = "    amount          = models.DecimalField(max_digits=15, decimal_places=2,\n                          default=Decimal('0'))\n    package_code    = models.CharField(max_length=20, blank=True, default='',\n                          help_text='TenderBoqPackage.code this line belongs to')\n    # Market intelligence (set from anonymised historical data)\n    market_rate_low"
if "package_code    = models.CharField" in t:
    print("already")
elif old not in t:
    raise SystemExit("not found")
else:
    p.write_text(t.replace(old, new, 1), encoding="utf-8")
    print("added")
