from pathlib import Path
p = Path("/app/templates/tenders/bid_workspace.html").read_text(encoding="utf-8")
checks = [
    "Apply Sub Contracting",
    "Apply selection",
    "Step 1 · Subcontracting first",
    "Print draft bid for approval",
    "Process — invite",
    ">Apply</button>",
]
for c in checks:
    print(f"{c!r}: {c in p}")
