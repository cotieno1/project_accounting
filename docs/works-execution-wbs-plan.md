# Works Execution / WBS — Contractor delivery from BOQ preambles to profit

**Status:** DRAFT for approval — nothing built yet. Do not write code until the
"Open decisions" section is signed off.

**Author/date:** Planning session, 2026‑07‑19.

**Goal (user's words):** Let Pioneer (or any contractor X) use the
*"BOQ Preambles — Measurement, Materials & Workmanship"* of a tender to create
**Task A → sub‑tasks A‑1, A‑2, A‑3 … n+1** to completion, with **sub‑task
completion certificates**, a **sub‑task inspection & approval** process, and a
back‑office **internal control system** using the *"Close Tender — Financial
Dashboard"* (ops‑dashboard) so delivery is **efficient and profitable**.

- Tender reference used throughout: `ED-AHP/001/2025-2026` (`/tenders/2/`).
- Contractor: Pioneer. Ops task: `TOMOG-PIONEER-HWF-00026` (`/ops-dashboard/`).

---

## 0. Status update (2026-07-19) - PHASE 1 BUILT

**Naming:** this workspace is branded as an INTERNAL PROCESS -
"Executing - Open Public Tender Project Task" - deliberately separated from the
public tender exchange (browse / bid / award). It is the contractor's own
delivery execution of the awarded works.


Task A -> sub-task A-1..n breakdown, the inspection/approval lifecycle, the
sub-task completion certificate, and an earned-value-vs-cost control panel are
implemented and tested (19 related tests passing). Phases 2-3 (exact
per-sub-task cost tagging, payment-certificate integration) remain.

Decisions taken for Phase 1:
- D1 (sub-task source): seeded from the BOQ preamble-derived compliance
  checkpoints grouped per trade/phase (each already carries its
  inspection/hold-point/certificate gate). A phase with no checkpoint gets one
  "execute & complete" step. Value = even share of the trade's milestone value.
- D2 (scope): breakdown + lifecycle + completion certificate + margin panel.
- D3 (entry point): contractor bid workspace -> "Works execution (WBS)".
- D6 (model home): buildwatch/models.py (WorkSubTask).

Phase 1 files:
- Model buildwatch/models.py::WorkSubTask + migration 0019_worksubtask.py
- Logic buildwatch/execution.py (generate_wbs_for_tender, wbs_overview, _finance_control)
- Views/URLs buildwatch/views_execution.py (works-execution, works-execution-action, works-subtask-cert)
- Templates templates/tenders/works_execution.html, works_subtask_certificate_print.html; entry link in bid_workspace.html
- Tests buildwatch/tests/test_works_execution.py (5 tests, passing)

## 1. Executive summary

About **80% of the machinery already exists**; it is just **sponsor‑facing** and
stops at *phase‑level* milestones. To deliver the request we need a
**contractor‑facing "Works Execution" workspace** that adds a **sub‑task layer**
under each trade/phase and wires each sub‑task to the **ops‑dashboard financials**
so Pioneer can see earned value vs cost = **margin** per slice of work.

We reuse (do **not** rebuild):
- BOQ preamble extraction + storage,
- the preamble → compliance‑checkpoint → phase → milestone (Gantt) chain,
- the inspection/approval sign‑off flow and certificate PDFs,
- the Pioneer budget/actuals/ledger rails.

Net‑new: **one model** (a contractor sub‑task) + contractor views/templates + a
**profitability rollup** that joins the two apps through the existing
`InfraProject.task → accounts.ProjectTask` link.

---

## 2. What already exists (reuse — no rebuild)

### 2.1 BuildWatch (sponsor / tender side) — `buildwatch/`
| Capability | Model / module | File |
|---|---|---|
| BOQ preambles (14 trade sections + lettered clauses) | `TenderPreamble` (`trade_code`, `title`, `body`, `source_page`) | `buildwatch/models.py`, extraction `buildwatch/boq_ingest/preambles.py` |
| Priced BOQ (employer bills + contractor prices) | `TenderBoqPackage`, `TenderBoqLine`, `WorkspaceBillPrice`, `BidWorkspace` | `buildwatch/models.py` |
| Inspection / hold‑point / certificate checkpoints from preambles | `ComplianceCheckpoint` (category, responsible/approver role, submit→approve/reject, evidence, `certificate_ref`) | `buildwatch/compliance.py`, `buildwatch/views_compliance.py` |
| Phase programme + Gantt milestones | `ProjectMilestone`, `_draft_programme`, `milestone_schedule` | `buildwatch/milestones.py`, `buildwatch/views_compliance.py` |
| Payment certificates (milestone‑gated) + PDFs | `PaymentCertificate`, sample‑certificate PDF | `buildwatch/views_delivery.py`, `views_compliance.py::compliance_sample_certificate` |
| Award / value‑for‑money rollup | `record_award`, `value_for_money` | `buildwatch/delivery.py` |

### 2.2 Pioneer (contractor / financial side) — `accounts/`
| Capability | Model / helper | File |
|---|---|---|
| Ops task (bare) | `ProjectTask` (`project_id`, `description`) | `accounts/models.py` |
| Budget (4 lines) + CEO lock/review | `ProjectBudget` (material/labour/misc/equipment), `BudgetReviewEvent` | `accounts/models.py` |
| Major lane spend | `BOMHeader/BOMItem` → `RequisitionOrder` → `LPOTransaction/LPOItem` → `GRNTransaction` → `PaymentOrder` (PV) | `accounts/models.py` |
| Ad‑hoc lane spend + completion/inspection + variance | `MiscRequisitionOrder`, `MiscPurchaseOrder` (`variation_status`), `MiscCompletionRecord`, `MiscVariation` | `accounts/models.py`, `accounts/misc_variation_views.py` |
| Budget‑vs‑actual / variance | `budget_overview`, `_task_disbursement_budget_summary`, `_task_budget_actual_spend` | `accounts/views.py` |
| GL / fund ledger | `accounts/ledger.py` (`task_fund_summary`, postings) | `accounts/ledger.py` |
| Ops hub | `fin_mgmt_ops_view` (`ops_dashboard`) | `accounts/views.py`, `templates/Fin_Mgmt_and_OPs_dashboard.html` |

### 2.3 The bridge that already connects both apps
- `buildwatch.InfraProject.task` is a **OneToOne → `accounts.ProjectTask`**.
- Contractor↔tender link: `Organization` → `BidderRegistration` → `BidWorkspace`
  → `Submission` (`is_awarded`), sponsor = `listing.event.project.owner_org`.

**Implication:** a BuildWatch tender/project is already joinable to a Pioneer
ops‑dashboard task — no new plumbing needed to reach the financials.

---

## 3. Gaps to close

1. **Contractor‑facing execution view.** The delivery hub today is on the
   procuring‑entity's "Tender Activity" page. Pioneer needs its own page to
   *drive* the work.
2. **Sub‑task layer.** Finest unit today = a phase milestone (e.g.
   "Substructure"). We need **Task A (trade/phase) → A‑1…n** operations.
3. **Execution ⇄ money link.** Nothing maps a *sub‑task* to its **earned value**
   (priced BOQ) vs **cost‑to‑date** (LPO/PV/labour) = **margin**. This is the
   "profitable delivery / internal control" the user is asking for.

---

## 4. Proposed architecture

```
Tender BOQ (priced)         BuildWatch delivery            Pioneer ops-dashboard
─────────────────           ───────────────────            ─────────────────────
TenderPreamble (Task A) ──► ProjectMilestone (phase)  ◄──► ProjectTask / ProjectBudget
   lettered clauses           │                              (material/labour/equip)
   priced BOQ lines           ▼                                     ▲
        └──────────► WorkSubTask (A-1…n)  NEW ───────────────────────┘
                        • inspection + approval  (link ComplianceCheckpoint)
                        • completion certificate (reuse cert PDF)
                        • earned value (BOQ) vs cost-to-date (LPO/PV/labour) = margin
```

### 4.1 New model (only one) — `WorkSubTask`
Proposed home: `buildwatch/models.py` (keeps it beside milestones/preambles;
still reachable from ops‑dashboard via the `ProjectTask` bridge).

Proposed fields (final list pending "Open decisions"):
- `milestone` FK → `ProjectMilestone` (the parent Task A / phase) — `related_name='subtasks'`
- `project` FK → `InfraProject` (denormalised for fast rollups)
- `seq` (int) and computed code label (e.g. `A-1`)
- `name`, `description`
- `preamble` FK → `TenderPreamble` (nullable — the governing trade rules)
- `boq_line` FK → `TenderBoqLine` (nullable) and/or `bill_ref` (the measured item it delivers)
- `checkpoint` FK → `ComplianceCheckpoint` (nullable — the inspection/approval gate)
- `planned_value` (Decimal — **earned value** from the priced BOQ or a share of the milestone value)
- `status` (PLANNED / IN_PROGRESS / INSPECTED / APPROVED / CERTIFIED / DONE)
- cost link fields for profitability (see 4.3)
- audit stamps (`created_by`, timestamps)

### 4.2 Reuse for inspection, approval, certificate
- **Inspection & approval:** link each `WorkSubTask` to a `ComplianceCheckpoint`
  and drive it through the existing `compliance_action`
  (submit → approve/reject, evidence upload, roles). No new sign‑off engine.
- **Sub‑task completion certificate:** reuse the certificate PDF path
  (`compliance_sample_certificate` / `payment_certificate_pdf`) parameterised for
  a sub‑task. Optionally gate a `PaymentCertificate` on sub‑task `APPROVED`.

### 4.3 Profitability / internal control (the back‑office control)
For each sub‑task compute:
- **Earned value** = `planned_value` (from the priced BOQ line) once `APPROVED`.
- **Cost‑to‑date** = committed/actual pulled from existing rails via
  `InfraProject.task → ProjectTask`:
  - materials: `LPOItem` / `PaymentOrder` (PV) allocated to the sub‑task,
  - ad‑hoc: `MiscPurchaseOrder` / `MiscCompletionRecord.actual_cost`,
  - labour/equipment: budget‑line disbursements (`TaskDisbursementPayment`).
- **Margin** = earned − cost; **cost‑to‑complete** = planned − cost.
- Roll up sub‑task → Task A (milestone) → project; surface a **margin panel** and
  a **gate** ("don't start A‑3 until A‑2 is inspected, certified, and within budget").

> Note: cost is currently tracked per **task** and per **4 budget lines**, not
> per sub‑task. The lightest first version allocates cost to sub‑tasks
> **pro‑rata by planned value** (accurate at Task‑A level, approximate per
> sub‑task). A later version can add an explicit sub‑task tag on LPO/PV lines for
> exact per‑sub‑task cost. (Decision D4.)

---

## 5. Views / URLs / templates (net‑new, contractor‑facing)
- `works-execution` page (per awarded tender/workspace): Task A list → expandable
  sub‑tasks with status, inspection state, certificate link, and a margin column.
- `works-execution-action` (POST): create/seed sub‑tasks from BOQ, start, request
  inspection, mark approved, issue completion certificate.
- Entry point: TBD (Decision D3) — bid workspace tab, ops‑dashboard lane, or both.
- Templates extend the existing shells (`buildwatch/base.html` for the tender side
  or `layouts/cockpit.html` for the ops side, depending on D3).

---

## 6. Delivery phases (proposed)
- **Phase 0 — this document + sign‑off of Open decisions.**
- **Phase 1 (read‑only insight):** contractor "Works Execution" page showing
  Task A → sub‑tasks (seeded from BOQ) with inspection status + a **margin/profit
  panel** (cost allocated pro‑rata). No new payment flows. *Lowest risk, fastest
  value.*
- **Phase 2 (control):** inspection request → approve/reject per sub‑task + **sub‑task
  completion certificate** PDF; gate the next sub‑task on approval + budget.
- **Phase 3 (exact costing + payment):** explicit sub‑task cost tagging on
  LPO/PV, milestone/certificate integration end‑to‑end.

---

## 7. Open decisions (must sign off before coding)
- **D1 — What is a "sub‑task A‑1…n" derived from?**
  (a) priced BOQ lines [recommended, ties to profit], (b) lettered preamble
  clauses, (c) both, (d) manual seeded from BOQ. *User indicated "other" — please
  specify exact meaning.*
- **D2 — Scope to build first:** Phase 1 only [recommended], full end‑to‑end, or
  design‑only.
- **D3 — Entry point:** bid workspace tab (`/tenders/2/bid/`), ops‑dashboard lane,
  or both.
- **D4 — Cost granularity:** pro‑rata allocation first [recommended] vs explicit
  per‑sub‑task cost tagging now.
- **D5 — Certificate authority:** who signs a sub‑task completion certificate on
  the contractor side (Site Eng / Snr Eng / QS) and does the sponsor/PM counter‑sign?
- **D6 — Model home:** `buildwatch/models.py` [recommended] vs `accounts/models.py`.

---

## 8. Non‑functional / housekeeping
- **Migration:** one `AddField`/`CreateModel` migration for `WorkSubTask`; keep it
  minimal (avoid the auto‑generated field‑drift noise — hand‑write like
  `0018_sop_shared.py`).
- **Tests:** WBS seeding from BOQ, inspection→approval transition, certificate
  render, margin rollup math.
- **Deploy:** Railway auto‑migrates on release (`scripts/railway_start.sh`); verify
  with `showmigrations` over SSH.
- **Permissions:** contractor can drive their own sub‑tasks; approver role per D5;
  sponsor read‑only into contractor execution (or hidden) — TBD.

---

## 9. Explicitly out of scope (for now)
- Rebuilding milestones/compliance/certificates (reuse existing).
- Changing `misc_purchase.html` or BOM lane behaviour (frozen per project rules).
- Any separate native Android UI (single codebase per project context).
