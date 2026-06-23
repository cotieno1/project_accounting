from django.core.management.base import BaseCommand

from accounts.quality.scorecard import run_quality_scorecard


class Command(BaseCommand):
    help = "Run the global quality checklist and print a weighted scorecard."

    def add_arguments(self, parser):
        parser.add_argument(
            "--min-score",
            type=float,
            default=None,
            help="Exit with code 1 if score percent is below this threshold (e.g. 90).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print machine-readable JSON summary.",
        )

    def handle(self, *args, **options):
        report = run_quality_scorecard()

        if options["json"]:
            import json

            payload = {
                "score": report.score,
                "max_score": report.max_score,
                "percent": report.percent,
                "categories": report.category_summary(),
                "failed": [
                    {
                        "id": r.check_id,
                        "category": r.category,
                        "title": r.title,
                        "detail": r.detail,
                    }
                    for r in report.failed
                ],
            }
            self.stdout.write(json.dumps(payload, indent=2))
        else:
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING("Project Accounting - Quality Scorecard"))
            self.stdout.write("")

            current_category = None
            for result in report.results:
                if result.category != current_category:
                    current_category = result.category
                    self.stdout.write(self.style.HTTP_INFO(f"\n[{current_category}]"))
                mark = self.style.SUCCESS("PASS") if result.passed else self.style.ERROR("FAIL")
                pts = f"+{result.weight}" if result.passed else f" 0/{result.weight}"
                self.stdout.write(f"  {mark} ({pts:>6}) {result.title}")
                if result.detail:
                    self.stdout.write(f"         {result.detail}")

            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING("Category scores"))
            for category, stats in report.category_summary().items():
                self.stdout.write(
                    f"  {category}: {stats['earned']}/{stats['max']} "
                    f"({stats['percent']}%) - {stats['failed']} failed"
                )

            self.stdout.write("")
            style = self.style.SUCCESS if report.percent >= 90 else self.style.WARNING
            if report.percent < 70:
                style = self.style.ERROR
            self.stdout.write(
                style(f"TOTAL: {report.score}/{report.max_score} ({report.percent}%)")
            )
            self.stdout.write("")
            self.stdout.write("Run regression tests: python manage.py test accounts.tests")
            self.stdout.write("")

        min_score = options["min_score"]
        if min_score is not None and report.percent < min_score:
            self.stderr.write(
                self.style.ERROR(
                    f"Score {report.percent}% is below minimum {min_score}%"
                )
            )
            raise SystemExit(1)