# -*- coding: utf-8 -*-
"""
BuildWatch Inception Engine - the layer BEFORE procurement / design.

Stage flow:
  CONCEPT -> WORKSHOP -> DOCUMENTED -> SPONSOR_REVIEW -> APPROVED -> DESIGN

Sector behaviour (budget lines, prompts, custody) comes from programme profiles,
not hardcoded housing fields on the core schema.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.utils import timezone


class ProjectInception(models.Model):
    """Pre-project collaboration workspace. Mints InfraProject on approval."""

    STAGE_CONCEPT = "CONCEPT"
    STAGE_WORKSHOP = "WORKSHOP"
    STAGE_DOCUMENTED = "DOCUMENTED"
    STAGE_SPONSOR_REVIEW = "SPONSOR_REVIEW"
    STAGE_APPROVED = "APPROVED"
    STAGE_DESIGN = "DESIGN"
    STAGE_CANCELLED = "CANCELLED"

    STAGE_CHOICES = [
        (STAGE_CONCEPT, "1 - Concept: Why this project?"),
        (STAGE_WORKSHOP, "2 - Workshop: Collaborative brief"),
        (STAGE_DOCUMENTED, "3 - Documented: Wish list & budget"),
        (STAGE_SPONSOR_REVIEW, "4 - Sponsor Review"),
        (STAGE_APPROVED, "5 - Approved - proceed to design"),
        (STAGE_DESIGN, "6 - In Design"),
        (STAGE_CANCELLED, "Cancelled"),
    ]

    SECTOR_CHOICES = [
        ("ROADS", "Roads & Bridges"),
        ("BUILDINGS", "Buildings"),
        ("WATER", "Water & Sanitation"),
        ("ENERGY", "Energy"),
        ("ICT", "ICT Infrastructure"),
        ("OTHER", "Other"),
    ]

    inception_ref = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        help_text="Auto-generated: INC-2026-001",
    )
    title = models.CharField(max_length=300, blank=True)
    profile_id = models.CharField(
        max_length=80,
        db_index=True,
        help_text="Programme profile id e.g. buildings.works, ict.telecom_operator",
    )
    sector = models.CharField(max_length=50, choices=SECTOR_CHOICES, default="OTHER")
    country = models.ForeignKey(
        "buildwatch.Country",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    county_region = models.CharField(max_length=100, blank=True)
    stage = models.CharField(
        max_length=20,
        choices=STAGE_CHOICES,
        default=STAGE_CONCEPT,
    )
    seed_project_ref = models.CharField(
        max_length=50,
        blank=True,
        help_text="Preferred ProjectTask id once approved (optional)",
    )

    sponsor_org = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.PROTECT,
        related_name="sponsored_inceptions",
    )
    sponsor_contact = models.ForeignKey(
        "accounts.UserAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inception_sponsor_contacts",
    )

    workshop_date = models.DateField(null=True, blank=True)
    workshop_venue = models.CharField(max_length=300, blank=True)

    # Living-brief custody / funding (profile supplies type ids)
    custody_type_id = models.CharField(max_length=80, blank=True)
    custody_status = models.CharField(max_length=40, default="UNKNOWN")
    custody_owner_note = models.CharField(max_length=500, blank=True)
    custody_route_note = models.CharField(max_length=500, blank=True)

    funding_type_id = models.CharField(max_length=80, blank=True)
    funding_status = models.CharField(max_length=40, default="UNFUNDED")
    funding_envelope = models.CharField(max_length=80, blank=True)
    funding_source_note = models.CharField(max_length=500, blank=True)

    activity_log = models.JSONField(default=list, blank=True)

    infra_project = models.OneToOneField(
        "buildwatch.InfraProject",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inception",
        help_text="Set when inception is approved and project is minted",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["sponsor_org", "stage"]),
            models.Index(fields=["sponsor_org", "profile_id"]),
        ]

    def __str__(self):
        return f"{self.inception_ref} - {self.title or self.profile_id}"

    def save(self, *args, **kwargs):
        if not self.inception_ref:
            year = timezone.now().year
            prefix = f"INC-{year}-"
            last = (
                ProjectInception.objects.filter(inception_ref__startswith=prefix)
                .order_by("-inception_ref")
                .first()
            )
            seq = 1
            if last:
                try:
                    seq = int(last.inception_ref.rsplit("-", 1)[-1]) + 1
                except ValueError:
                    seq = (
                        ProjectInception.objects.filter(
                            inception_ref__startswith=prefix
                        ).count()
                        + 1
                    )
            self.inception_ref = f"{prefix}{seq:03d}"
        super().save(*args, **kwargs)

    @property
    def stage_number(self) -> int:
        order = [
            self.STAGE_CONCEPT,
            self.STAGE_WORKSHOP,
            self.STAGE_DOCUMENTED,
            self.STAGE_SPONSOR_REVIEW,
            self.STAGE_APPROVED,
            self.STAGE_DESIGN,
        ]
        try:
            return order.index(self.stage) + 1
        except ValueError:
            return 0

    @property
    def minted_project_id(self) -> str:
        if self.infra_project_id and self.infra_project:
            return self.infra_project.task_id
        return ""


class InceptionParticipant(models.Model):
    """Person invited to contribute. Roles: SPONSOR / BUSINESS / TECHNICAL."""

    SPONSOR = "SPONSOR"
    BUSINESS = "BUSINESS"
    TECHNICAL = "TECHNICAL"

    ROLE_CHOICES = [
        (SPONSOR, "Sponsor - project rationale and funding"),
        (BUSINESS, "Business - needs, requirements, users"),
        (TECHNICAL, "Technical - design viability and budget"),
    ]

    inception = models.ForeignKey(
        ProjectInception,
        on_delete=models.CASCADE,
        related_name="participants",
    )
    user = models.ForeignKey(
        "accounts.UserAccount",
        on_delete=models.PROTECT,
        related_name="inception_participations",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    organisation = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.PROTECT,
        related_name="inception_participations",
    )
    technical_discipline = models.CharField(
        max_length=50,
        blank=True,
        help_text="e.g. Quantity Surveyor, Architect, RF Planner",
    )
    invited_at = models.DateTimeField(auto_now_add=True)
    accepted = models.BooleanField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [["inception", "user"]]
        ordering = ["role", "invited_at"]

    def __str__(self):
        org = getattr(self.organisation, "short_name", "") or ""
        return f"{self.get_role_display()} - {self.user} ({org})"


class WorkshopContribution(models.Model):
    """
    Structured contribution. Type codes are profile-driven for lanes
    (mandate / requirements / feasibility) and may also use buildings pack
    codes (SPONSOR_WHY, TECH_BUDGET, ...).
    """

    # Buildings / classic pack codes (optional; not enforced at DB level)
    SPONSOR_WHY = "SPONSOR_WHY"
    SPONSOR_FUNDING = "SPONSOR_FUNDING"
    SPONSOR_OUTCOME = "SPONSOR_OUTCOME"
    BUSINESS_NEED = "BUSINESS_NEED"
    BUSINESS_USERS = "BUSINESS_USERS"
    BUSINESS_WISHLIST = "BUSINESS_WISHLIST"
    BUSINESS_PRIORITY = "BUSINESS_PRIORITY"
    TECH_SITE = "TECH_SITE"
    TECH_CONCEPT = "TECH_CONCEPT"
    TECH_STRUCTURE = "TECH_STRUCTURE"
    TECH_STANDARDS = "TECH_STANDARDS"
    TECH_RISKS = "TECH_RISKS"
    TECH_BUDGET = "TECH_BUDGET"
    TECH_PROGRAMME = "TECH_PROGRAMME"

    # Universal living-brief lane ids (all profiles)
    LANE_MANDATE = "mandate"
    LANE_REQUIREMENTS = "requirements"
    LANE_FEASIBILITY = "feasibility"

    inception = models.ForeignKey(
        ProjectInception,
        on_delete=models.CASCADE,
        related_name="contributions",
    )
    participant = models.ForeignKey(
        InceptionParticipant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contributions",
    )
    contribution_type = models.CharField(
        max_length=40,
        db_index=True,
        help_text="Profile or lane code e.g. mandate, SPONSOR_WHY",
    )
    content = models.TextField(blank=True)
    attachments = models.FileField(
        upload_to="inception/contributions/%Y/%m/",
        null=True,
        blank=True,
    )
    is_final = models.BooleanField(default=False)
    updated_by_name = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["contribution_type", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["inception", "contribution_type"],
                name="uniq_inception_contribution_type",
            )
        ]

    def __str__(self):
        return f"{self.inception.inception_ref} | {self.contribution_type}"


class ConceptBudget(models.Model):
    """
    High-level OME / elemental budget at inception.
    Line items are profile-seeded (buildings pack = classic elemental rows).
    """

    ACCURACY_CHOICES = [
        ("PM30", "+/-30% - Order of magnitude"),
        ("PM20", "+/-20% - Scheme design"),
        ("PM10", "+/-10% - Detail design"),
        ("PM5", "+/-5% - Pre-tender estimate"),
    ]

    inception = models.OneToOneField(
        ProjectInception,
        on_delete=models.CASCADE,
        related_name="concept_budget",
    )
    prepared_by = models.ForeignKey(
        "accounts.UserAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prepared_concept_budgets",
    )
    currency = models.CharField(max_length=10, default="KES")
    basis_of_estimate = models.TextField(blank=True)
    accuracy = models.CharField(
        max_length=5,
        choices=ACCURACY_CHOICES,
        default="PM30",
    )
    is_approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        "accounts.UserAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_concept_budgets",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Concept Budget - {self.inception.inception_ref}"

    @property
    def total_amount(self) -> Decimal:
        total = Decimal("0")
        for line in self.lines.all():
            total += line.amount or Decimal("0")
        return total


class ConceptBudgetLine(models.Model):
    """One profile-defined cost line on a concept budget."""

    budget = models.ForeignKey(
        ConceptBudget,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    code = models.CharField(max_length=40)
    label = models.CharField(max_length=200)
    group = models.CharField(
        max_length=40,
        blank=True,
        help_text="e.g. construction, fees, contingency, client",
    )
    amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0"),
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        unique_together = [["budget", "code"]]

    def __str__(self):
        return f"{self.code} - {self.label}"


class InceptionDocument(models.Model):
    """Evidence / attachment on the inception workspace."""

    SKETCH = "SKETCH"
    SITE_PHOTO = "SITE_PHOTO"
    REFERENCE = "REFERENCE"
    PLANNING = "PLANNING"
    ENVIRONMENTAL = "ENVIRONMENTAL"
    BUDGET_WORKINGS = "BUDGET_WORKINGS"
    OTHER = "OTHER"

    DOC_TYPE_CHOICES = [
        (SKETCH, "Architectural Sketch / Concept Drawing"),
        (SITE_PHOTO, "Site Photograph"),
        (REFERENCE, "Reference Project"),
        (PLANNING, "Planning / Zoning Document"),
        (ENVIRONMENTAL, "Environmental Assessment"),
        (BUDGET_WORKINGS, "Budget Workings / Cost Data"),
        (OTHER, "Other"),
    ]

    inception = models.ForeignKey(
        ProjectInception,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    uploaded_by = models.ForeignKey(
        "accounts.UserAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    doc_type = models.CharField(max_length=20, choices=DOC_TYPE_CHOICES, default=OTHER)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to="inception/documents/%Y/%m/", blank=True)
    is_final = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["doc_type", "-uploaded_at"]

    def __str__(self):
        return f"{self.get_doc_type_display()} - {self.title}"


class InceptionApproval(models.Model):
    """
    Formal sponsor decision. APPROVED advances stage and (via service) mints
    InfraProject / ProjectTask.
    """

    APPROVED = "APPROVED"
    REVISE = "REVISE"
    CANCELLED = "CANCELLED"

    ACTION_CHOICES = [
        (APPROVED, "Approved - proceed to design"),
        (REVISE, "Revise - return to workshop"),
        (CANCELLED, "Cancelled - project not proceeding"),
    ]

    inception = models.ForeignKey(
        ProjectInception,
        on_delete=models.PROTECT,
        related_name="approvals",
    )
    actioned_by = models.ForeignKey(
        "accounts.UserAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    actioned_by_name = models.CharField(max_length=80, blank=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    comments = models.TextField(blank=True)
    approved_budget = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
    )
    currency = models.CharField(max_length=10, default="KES")
    minted_project_id = models.CharField(max_length=50, blank=True)
    actioned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-actioned_at"]

    def __str__(self):
        return f"{self.inception.inception_ref} - {self.get_action_display()}"
