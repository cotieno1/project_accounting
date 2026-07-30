# -*- coding: utf-8 -*-
"""
Project Work Plan - post-concept delivery planning on an InfraProject.

Covers:
  - Rollout breakdown (strategic stagger): test -> pilot/waves -> commissioning
  - Financing tranches aligned to those phases
  - Programme BOM (materials / equipment) that can later feed Pioneer BOMHeader

Sector defaults come from programme profile `work_plan` packs.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.db.models import Sum
from django.utils import timezone


class ProjectWorkPlan(models.Model):
    """One living work plan per InfraProject (created in DESIGN after inception)."""

    STATUS_DRAFT = "DRAFT"
    STATUS_APPROVED = "APPROVED"
    STATUS_ACTIVE = "ACTIVE"
    STATUS_CLOSED = "CLOSED"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_ACTIVE, "Active rollout"),
        (STATUS_CLOSED, "Closed"),
    ]

    infra_project = models.OneToOneField(
        "buildwatch.InfraProject",
        on_delete=models.CASCADE,
        related_name="work_plan",
    )
    inception = models.ForeignKey(
        "buildwatch.ProjectInception",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="work_plans",
    )
    profile_id = models.CharField(max_length=80, blank=True)
    title = models.CharField(max_length=300, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
    )
    currency = models.CharField(max_length=10, default="KES")
    total_envelope = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Strategic financing envelope for the rollout programme",
    )
    strategy_note = models.TextField(
        blank=True,
        help_text="How waves are staggered and why (coverage, cash, logistics)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title or f"Work plan {self.pk}"

    @property
    def financing_allocated(self) -> Decimal:
        agg = self.phases.aggregate(t=Sum("financing_amount"))
        return agg["t"] or Decimal("0")

    @property
    def bom_total(self) -> Decimal:
        total = Decimal("0")
        for line in self.bom_lines.all():
            total += line.line_total
        return total


class WorkPlanPhase(models.Model):
    """One stage in the rollout: test, pilot, wave, commissioning, etc."""

    KIND_TEST = "TEST"
    KIND_PILOT = "PILOT"
    KIND_WAVE = "WAVE"
    KIND_INTEGRATION = "INTEGRATION"
    KIND_COMMISSIONING = "COMMISSIONING"
    KIND_HANDOVER = "HANDOVER"
    KIND_OTHER = "OTHER"
    KIND_CHOICES = [
        (KIND_TEST, "Test / proof"),
        (KIND_PILOT, "Pilot"),
        (KIND_WAVE, "Rollout wave"),
        (KIND_INTEGRATION, "Integration / acceptance"),
        (KIND_COMMISSIONING, "Commissioning"),
        (KIND_HANDOVER, "Handover"),
        (KIND_OTHER, "Other"),
    ]

    plan = models.ForeignKey(
        ProjectWorkPlan,
        on_delete=models.CASCADE,
        related_name="phases",
    )
    code = models.CharField(max_length=40)
    label = models.CharField(max_length=200)
    kind = models.CharField(
        max_length=20,
        choices=KIND_CHOICES,
        default=KIND_WAVE,
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    objective = models.TextField(blank=True)
    exit_criteria = models.TextField(
        blank=True,
        help_text="What must be true before the next phase starts",
    )
    planned_start = models.DateField(null=True, blank=True)
    planned_end = models.DateField(null=True, blank=True)
    site_or_scope = models.CharField(
        max_length=300,
        blank=True,
        help_text="e.g. 10 pilot BTS sites / Juba corridor",
    )
    financing_pct = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0"),
        help_text="% of programme envelope released for this phase",
    )
    financing_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
    )
    financing_trigger = models.CharField(
        max_length=200,
        blank=True,
        help_text="e.g. Pilot acceptance signed / Wave-1 RF complete",
    )
    is_complete = models.BooleanField(default=False)

    class Meta:
        ordering = ["sort_order", "id"]
        unique_together = [["plan", "code"]]

    def __str__(self):
        return f"{self.code} - {self.label}"


class WorkPlanBomLine(models.Model):
    """
    Programme BOM line for the work plan (equipment / materials / civil kits).
    Optional link to a rollout phase. Can later sync into accounts.BOMHeader.
    """

    plan = models.ForeignKey(
        ProjectWorkPlan,
        on_delete=models.CASCADE,
        related_name="bom_lines",
    )
    phase = models.ForeignKey(
        WorkPlanPhase,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bom_lines",
    )
    item_code = models.CharField(max_length=50, blank=True)
    description = models.CharField(max_length=300)
    unit = models.CharField(max_length=20, default="Nr")
    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
    )
    unit_cost = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.description

    @property
    def line_total(self) -> Decimal:
        return (self.quantity or Decimal("0")) * (self.unit_cost or Decimal("0"))


class WorkPlanActivity(models.Model):
    """Lightweight activity log on the work plan."""

    plan = models.ForeignKey(
        ProjectWorkPlan,
        on_delete=models.CASCADE,
        related_name="activities",
    )
    at = models.DateTimeField(default=timezone.now)
    who = models.CharField(max_length=80, blank=True)
    text = models.CharField(max_length=400)

    class Meta:
        ordering = ["-at"]
