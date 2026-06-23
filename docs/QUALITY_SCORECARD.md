# Project Accounting — Quality Scorecard

Weighted checklist to catch production flaws before deploy (mobile UX, template corruption, empty prints, MRO task path).

## Run the scorecard

```bash
python manage.py quality_scorecard
```

JSON output (CI / scripts):

```bash
python manage.py quality_scorecard --json
```

Fail deploy if score drops below 90%:

```bash
python manage.py quality_scorecard --min-score 90
```

## Run regression tests

```bash
python manage.py test accounts.tests
```

## Categories (100 points total)

| Category | Points | What it guards |
|----------|--------|----------------|
| Mobile & responsive UX | 30 | Workspace task picker outside transformed sidebar; mobile CSS; cockpit hamburger |
| Template integrity | 25 | UTF-8 flash template, balanced if tags, task descriptions in picker |
| Print & workflow guards | 25 | Empty-document print blocks, print_items_count, main-menu flash link |
| Misc MRO task path | 20 | misc_purchase_task_list, URL encoding, mobile regression tests |

## Railway deploy

scripts/railway_start.sh runs the scorecard after migrations (non-blocking log). Set BLOCK_DEPLOY_ON_QUALITY_FAILURE=1 to block deploy when score is below 90%. Set RUN_TESTS_ON_DEPLOY=1 to run tests on deploy.
