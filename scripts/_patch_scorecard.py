from pathlib import Path
p = Path("accounts/quality/scorecard.py")
text = p.read_text(encoding="utf-8")
old = """        \"id\": \"mro.regression_tests\",
        \"category\": \"Misc MRO task path\",
        \"title\": \"Misc purchase mobile regression tests present\",
        \"weight\": 7,
        \"run\": lambda: (
            _ok()
            if Path(settings.BASE_DIR / \"accounts/tests/test_misc_purchase_mobile.py\").is_file()
            else _fail(\"Add accounts/tests/test_misc_purchase_mobile.py\")
        ),
    },
]"""
new = """        \"id\": \"mro.regression_tests\",
        \"category\": \"Misc MRO task path\",
        \"title\": \"Misc purchase mobile regression tests present\",
        \"weight\": 4,
        \"run\": lambda: (
            _ok()
            if Path(settings.BASE_DIR / \"accounts/tests/test_misc_purchase_mobile.py\").is_file()
            else _fail(\"Add accounts/tests/test_misc_purchase_mobile.py\")
        ),
    },
    {
        \"id\": \"mro.pdf_table_widths\",
        \"category\": \"Misc MRO task path\",
        \"title\": \"print_mro.html PDF mode uses explicit table widths (xhtml2pdf)\",
        \"weight\": 3,
        \"run\": lambda: (
            _ok()
            if \"{% if for_pdf %}\" in _read(\"templates/print_mro.html\")
            and 'width=\"5%\"' in _read(\"templates/print_mro.html\")
            and Path(settings.BASE_DIR / \"accounts/tests/test_mro_pdf.py\").is_file()
            else _fail(\"print_mro PDF layout guards missing\")
        ),
    },
]"""
if "mro.pdf_table_widths" not in text:
    text = text.replace(old, new)
    p.write_text(text, encoding="utf-8")
    print("patched")
else:
    print("already")
