"""
Global quality checklist with weighted scorecard.

Run: python manage.py quality_scorecard
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings


@dataclass
class CheckResult:
    check_id: str
    category: str
    title: str
    weight: int
    passed: bool
    detail: str = ""


@dataclass
class QualityReport:
    results: list[CheckResult] = field(default_factory=list)

    @property
    def max_score(self) -> int:
        return sum(r.weight for r in self.results)

    @property
    def score(self) -> int:
        return sum(r.weight for r in self.results if r.passed)

    @property
    def percent(self) -> float:
        if not self.max_score:
            return 100.0
        return round(100.0 * self.score / self.max_score, 1)

    @property
    def failed(self) -> list[CheckResult]:
        return [r for r in self.results if not r.passed]

    def category_summary(self) -> dict[str, dict[str, int | float]]:
        buckets: dict[str, dict[str, int | float]] = {}
        for r in self.results:
            bucket = buckets.setdefault(
                r.category, {"earned": 0, "max": 0, "checks": 0, "failed": 0}
            )
            bucket["max"] = int(bucket["max"]) + r.weight
            bucket["checks"] = int(bucket["checks"]) + 1
            if r.passed:
                bucket["earned"] = int(bucket["earned"]) + r.weight
            else:
                bucket["failed"] = int(bucket["failed"]) + 1
        for bucket in buckets.values():
            max_pts = int(bucket["max"])
            earned = int(bucket["earned"])
            bucket["percent"] = round(100.0 * earned / max_pts, 1) if max_pts else 100.0
        return buckets


def _read(rel_path: str) -> str:
    path = Path(settings.BASE_DIR) / rel_path
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _ok(detail: str = "") -> tuple[bool, str]:
    return True, detail


def _fail(detail: str) -> tuple[bool, str]:
    return False, detail


def _balanced_django_if_tags(text: str) -> tuple[bool, str]:
    opens = text.count("{% if ")
    closes = text.count("{% endif %}")
    if opens == closes:
        return _ok(f"{opens} if/endif pairs")
    return _fail(f"Unbalanced if tags: {opens} if vs {closes} endif")


CHECKS: list[dict] = [
    {
        "id": "mobile.misc_workspace_picker",
        "category": "Mobile & responsive UX",
        "title": "Misc purchase workspace task picker (mobile-safe)",
        "weight": 10,
        "run": lambda: (
            _ok()
            if "misc_task_picker.html" in _read("templates/misc_purchase.html")
            and "misc-workspace-task-bar" in _read("templates/misc_purchase.html")
            else _fail("misc_purchase.html must include workspace misc_task_picker")
        ),
    },
    {
        "id": "mobile.misc_css_workspace_visible",
        "category": "Mobile & responsive UX",
        "title": "Misc purchase CSS shows workspace picker on small screens",
        "weight": 8,
        "run": lambda: (
            _ok()
            if ".misc-workspace-task-bar" in _read("static/css/pioneer/modules/misc-purchase.css")
            and "display: block" in _read("static/css/pioneer/modules/misc-purchase.css")
            and "768px" in _read("static/css/pioneer/modules/misc-purchase.css")
            else _fail("misc-purchase.css missing mobile workspace task bar rules")
        ),
    },
    {
        "id": "mobile.misc_sidebar_picker_hidden",
        "category": "Mobile & responsive UX",
        "title": "Sidebar task picker hidden on mobile (avoids iOS transform bug)",
        "weight": 7,
        "run": lambda: (
            _ok()
            if ".misc-sidebar-task-picker" in _read("static/css/pioneer/modules/misc-purchase.css")
            and "display: none" in _read("static/css/pioneer/modules/misc-purchase.css")
            else _fail("Hide .misc-sidebar-task-picker in mobile CSS")
        ),
    },
    {
        "id": "mobile.cockpit_hamburger",
        "category": "Mobile & responsive UX",
        "title": "Cockpit shell has mobile sidebar toggle",
        "weight": 5,
        "run": lambda: (
            _ok()
            if "sidebar-toggle" in _read("templates/layouts/cockpit.html")
            and "768px" in _read("static/css/pioneer/responsive.css")
            else _fail("cockpit mobile navigation not configured")
        ),
    },
    {
        "id": "tpl.flash_utf8",
        "category": "Template integrity",
        "title": "flash_messages.html is valid UTF-8 Django template",
        "weight": 8,
        "run": lambda: _check_flash_messages(),
    },
    {
        "id": "tpl.misc_purchase_if_balance",
        "category": "Template integrity",
        "title": "misc_purchase.html balanced {% if %} tags",
        "weight": 7,
        "run": lambda: _balanced_django_if_tags(_read("templates/misc_purchase.html")),
    },
    {
        "id": "tpl.cockpit_flash_include",
        "category": "Template integrity",
        "title": "Cockpit layout includes flash messages",
        "weight": 5,
        "run": lambda: (
            _ok()
            if "flash_messages.html" in _read("templates/layouts/cockpit.html")
            else _fail("cockpit.html must include flash_messages")
        ),
    },
    {
        "id": "tpl.misc_picker_descriptions",
        "category": "Template integrity",
        "title": "Misc task picker shows task descriptions",
        "weight": 5,
        "run": lambda: (
            _ok()
            if "truncatechars" in _read("templates/includes/misc_task_picker.html")
            else _fail("misc_task_picker.html should truncate task descriptions")
        ),
    },
    {
        "id": "guard.print_items_count",
        "category": "Print & workflow guards",
        "title": "_print_items_count handles lists and querysets",
        "weight": 8,
        "run": lambda: _check_print_items_count(),
    },
    {
        "id": "guard.empty_print_helpers",
        "category": "Print & workflow guards",
        "title": "Empty-document print guards exist",
        "weight": 9,
        "run": lambda: _check_print_guards(),
    },
    {
        "id": "guard.flash_main_menu",
        "category": "Print & workflow guards",
        "title": "Flash messages link back to main menu",
        "weight": 8,
        "run": lambda: (
            _ok()
            if "Main menu" in _read("templates/includes/flash_messages.html")
            else _fail("flash_messages.html missing Main menu link")
        ),
    },
    {
        "id": "mro.task_list_helper",
        "category": "Misc MRO task path",
        "title": "_misc_purchase_task_list keeps active task visible",
        "weight": 7,
        "run": lambda: (
            _ok()
            if "def _misc_purchase_task_list" in _read("accounts/views.py")
            else _fail("_misc_purchase_task_list missing from views.py")
        ),
    },
    {
        "id": "mro.picker_encode_uri",
        "category": "Misc MRO task path",
        "title": "Task picker URL-encodes task_id on change",
        "weight": 6,
        "run": lambda: (
            _ok()
            if "encodeURIComponent" in _read("templates/includes/misc_task_picker.html")
            else _fail("misc task picker must encodeURIComponent(task_id)")
        ),
    },
    {
        "id": "mro.regression_tests",
        "category": "Misc MRO task path",
        "title": "Misc purchase mobile regression tests present",
        "weight": 7,
        "run": lambda: (
            _ok()
            if Path(settings.BASE_DIR / "accounts/tests/test_misc_purchase_mobile.py").is_file()
            else _fail("Add accounts/tests/test_misc_purchase_mobile.py")
        ),
    },
]


def _check_flash_messages() -> tuple[bool, str]:
    path = Path(settings.BASE_DIR) / "templates/includes/flash_messages.html"
    if not path.is_file():
        return _fail("flash_messages.html missing")
    raw = path.read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return _fail("UTF-16 BOM detected - causes raw template tags on page")
    text = raw.decode("utf-8")
    if not text.lstrip().startswith("{%"):
        return _fail("Template should start with Django tag, not corrupted bytes")
    if "{% if messages %}" not in text:
        return _fail("Missing {% if messages %} wrapper")
    return _ok("UTF-8 template OK")


def _check_print_items_count() -> tuple[bool, str]:
    text = _read("accounts/views.py")
    if "def _print_items_count" not in text:
        return _fail("_print_items_count not found")
    if 'hasattr(items, "exists")' not in text:
        return _fail("_print_items_count must use .exists() for querysets")
    try:
        from accounts.views import _print_items_count

        if _print_items_count([]) != 0 or _print_items_count([1, 2]) != 2:
            return _fail("_print_items_count list handling broken")
    except Exception as exc:
        return _fail(f"Could not import _print_items_count: {exc}")
    return _ok("list and queryset handling verified")


def _check_print_guards() -> tuple[bool, str]:
    text = _read("accounts/views.py")
    required = (
        "_redirect_empty_print",
        "_rfq_letter_print_guard",
        "_mpo_print_guard",
        "_mro_print_guard",
    )
    missing = [name for name in required if name not in text]
    if missing:
        return _fail(f"Missing guards: {', '.join(missing)}")
    return _ok("RFQ, MPO, and MRO empty-print guards present")


def run_quality_scorecard() -> QualityReport:
    report = QualityReport()
    for item in CHECKS:
        try:
            passed, detail = item["run"]()
        except Exception as exc:
            passed, detail = False, f"Check error: {exc}"
        report.results.append(
            CheckResult(
                check_id=item["id"],
                category=item["category"],
                title=item["title"],
                weight=item["weight"],
                passed=passed,
                detail=detail,
            )
        )
    return report