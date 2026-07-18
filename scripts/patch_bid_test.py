from pathlib import Path

p = Path("accounts/tests/test_bid_evaluation_gate.py")
t = p.read_text(encoding="utf-8")
t = t.replace("no procurement path yet", "no man's land")
if "Abandon (Esc)" not in t:
    t = t.replace(
        'self.assertContains(response, "bid-eval-lane-choice")\n        self.assertNotContains(response, "Select Two Bidders")',
        'self.assertContains(response, "bid-eval-lane-choice")\n        self.assertContains(response, "Abandon (Esc)")\n        self.assertNotContains(response, "Select Two Bidders")',
    )
p.write_text(t, encoding="utf-8")
print("patched")
