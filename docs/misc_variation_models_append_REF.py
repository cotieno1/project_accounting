# ============================================================================
# BUILDWATCH ADDENDUM A — append these models to accounts/models.py
# after the existing MiscPurchaseOrder and CashClearingRecord models.
# Migration: 0040_misc_variation_buildwatch_link.py
# ============================================================================

from decimal import Decimal


# ── STEP 1: Extend MiscPurchaseOrder.save() ──────────────────────────────────
# Add this to the existing MiscPurchaseOrder.save() method:
#
#   def save(self, *args, **kwargs):
#       # ── NEW: Enforce CEO ceiling ─────────────────────────────────────
#       if self.ceiling_locked and self.budget_ceiling is not None:
#           if self.total_amount > self.budget_ceiling:
#               raise ValueError(
#                   f'Total amount KES {self.total_amount} exceeds '
#                   f'CEO-approved ceiling KES {self.budget_ceiling}. '
#                   f'A new CEO approval is required.'
#               )
#       # ── NEW: Auto-assign variation_ref within the project ────────────
#       if self.infra_project and not self.variation_ref:
#           existing = MiscPurchaseOrder.objects.filter(
#               infra_project=self.infra_project,
#               variation_ref__startswith='MV-'
#           ).count()
#           self.variation_ref = f'MV-{existing + 1:03d}'
#       # ── existing MPO number logic continues below ────────────────────
#       if not self.mpo_number:
#           pass  # existing generation logic unchanged
#       super().save(*args, **kwargs)
# ─────────────────────────────────────────────────────────────────────────────


class MiscCompletionRecord(models.Model):
    """
    The GRN-equivalent for self-executed misc variations.

    Senior Engineer signs off that the physical work is done and uploads
    photographic evidence. Required before CashClearingRecord can be raised
    (GL close gate). Without this record, Finance cannot reconcile the MPO.

    Flow:
        MiscPurchaseOrder (ACTIVE)
            → Senior Engineer creates MiscCompletionRecord
            → MiscPurchaseOrder.variation_status → PENDING_SIGNOFF
            → Finance raises CashClearingRecord (gate now open)
            → MiscVariation.status → RECONCILED
    """
    mpo = models.OneToOneField(
        MiscPurchaseOrder,
        on_delete=models.PROTECT,
        related_name='completion_record',
    )
    completed_by = models.ForeignKey(
        'UserAccount',
        on_delete=models.PROTECT,
        related_name='misc_completions_signed',
        help_text='Senior Engineer who physically inspects and signs off the work.',
    )
    scope_achieved = models.TextField(
        help_text='Plain-English description of what was physically completed.',
    )
    photo_1 = models.ImageField(
        upload_to='misc_completions/%Y/%m/',
        help_text='Required: photograph of completed work (before/after preferred).',
    )
    photo_2 = models.ImageField(
        upload_to='misc_completions/%Y/%m/',
        null=True,
        blank=True,
    )
    photo_3 = models.ImageField(
        upload_to='misc_completions/%Y/%m/',
        null=True,
        blank=True,
    )
    actual_cost = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text='Total actual spend confirmed from receipts.',
    )
    variance_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0'),
        help_text='actual_cost minus budget_ceiling. Negative = underspend (good).',
    )
    quality_notes = models.TextField(
        blank=True,
        default='',
        help_text='Punch list, quality observations, or follow-up required.',
    )
    signed_off_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Misc Completion Record'
        verbose_name_plural = 'Misc Completion Records'

    def save(self, *args, **kwargs):
        # Auto-compute variance vs ceiling
        if self.mpo.budget_ceiling and self.actual_cost is not None:
            self.variance_amount = self.actual_cost - self.mpo.budget_ceiling
        super().save(*args, **kwargs)
        # Advance MPO to PENDING_SIGNOFF — unlocks Finance reconciliation
        MiscPurchaseOrder.objects.filter(pk=self.mpo_id).update(
            variation_status='PENDING_SIGNOFF'
        )

    def __str__(self):
        return f'Completion: {self.mpo.variation_ref or self.mpo.mpo_number}'

    @property
    def is_underspend(self):
        return self.variance_amount <= Decimal('0')

    @property
    def variance_pct(self):
        if self.mpo.budget_ceiling and self.mpo.budget_ceiling > 0:
            return (self.variance_amount / self.mpo.budget_ceiling * 100).quantize(
                Decimal('0.01')
            )
        return Decimal('0')


class MiscVariation(models.Model):
    """
    Thin wrapper that registers a MiscPurchaseOrder as a named variation
    in the BuildWatch project variation account.

    Mirrors execution.VariationOrder (Type A) so both variation types
    appear in the unified variation register on the project dashboard.

    Created automatically when the CEO approves the MiscPurchaseOrder ceiling.
    """
    mpo = models.OneToOneField(
        MiscPurchaseOrder,
        on_delete=models.PROTECT,
        related_name='variation_record',
    )
    project = models.ForeignKey(
        'buildwatch.InfraProject',
        on_delete=models.PROTECT,
        related_name='misc_variation_records',
    )
    variation_type = models.CharField(
        max_length=20,
        default='MISC_SELF_EXECUTE',
        editable=False,
        help_text='Always MISC_SELF_EXECUTE. Type A subcontract variations use execution.VariationOrder.',
    )
    # Human-readable ref: MV-001, MV-002 … per project
    ref = models.CharField(max_length=20)
    description = models.CharField(max_length=500)
    approved_value = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0'),
        help_text='CEO-approved ceiling. Set at time of approval.',
    )
    actual_value = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0'),
        help_text='Actual cost from MiscCompletionRecord. Set at reconciliation.',
    )

    STATUS_CHOICES = [
        ('DRAFT',       'Draft'),
        ('APPROVED',    'CEO Approved'),
        ('ACTIVE',      'Active — work in progress'),
        ('RECONCILED',  'Reconciled — GL closed'),
        ('CANCELLED',   'Cancelled'),
    ]
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default='DRAFT',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reconciled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['ref']
        verbose_name = 'Misc Variation'
        verbose_name_plural = 'Misc Variations'

    def __str__(self):
        return f'{self.ref} — {self.description[:60]}'

    @property
    def is_within_contingency(self):
        """True if cumulative misc variations for this project are within the contingency."""
        total_others = MiscVariation.objects.filter(
            project=self.project,
            status__in=['APPROVED', 'ACTIVE', 'RECONCILED'],
        ).exclude(pk=self.pk).aggregate(
            t=models.Sum('approved_value')
        )['t'] or Decimal('0')
        try:
            contingency = self.project.task.budget.misc_reserve or Decimal('0')
        except Exception:
            return True  # No budget set — don't block
        return (total_others + self.approved_value) <= contingency

    @property
    def contingency_pct(self):
        """Percentage of project contingency consumed by all misc variations."""
        try:
            contingency = self.project.task.budget.misc_reserve or Decimal('0')
            if not contingency:
                return Decimal('0')
            total = MiscVariation.objects.filter(
                project=self.project,
                status__in=['APPROVED', 'ACTIVE', 'RECONCILED'],
            ).aggregate(t=models.Sum('approved_value'))['t'] or Decimal('0')
            return (total / contingency * 100).quantize(Decimal('0.1'))
        except Exception:
            return Decimal('0')
