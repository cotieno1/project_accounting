"""Tests for the global quality scorecard engine."""

from django.test import TestCase

from accounts.quality.scorecard import run_quality_scorecard


class QualityScorecardTests(TestCase):
    def test_scorecard_runs_and_meets_baseline(self):
        report = run_quality_scorecard()
        self.assertGreater(report.max_score, 0)
        self.assertGreaterEqual(report.percent, 90.0, report.failed)
        self.assertFalse(
            [r for r in report.failed if r.check_id == "mobile.misc_workspace_picker"],
            "Mobile workspace picker check must pass after fix",
        )

    def test_category_summary_matches_results(self):
        report = run_quality_scorecard()
        summary = report.category_summary()
        for category, stats in summary.items():
            cat_results = [r for r in report.results if r.category == category]
            self.assertEqual(int(stats["max"]), sum(r.weight for r in cat_results))
            self.assertEqual(
                int(stats["earned"]),
                sum(r.weight for r in cat_results if r.passed),
            )