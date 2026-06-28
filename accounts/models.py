from django.db import models
from django.contrib.auth.models import User
import uuid
from decimal import Decimal
#from django.db import models
from django.utils import timezone
# ... (rest of your imports)

from django.core.validators import MinValueValidator

quantity = models.DecimalField(
    max_digits=12,
    decimal_places=2,
    validators=[MinValueValidator(0)]
)

class Module(models.Model):
    name = models.CharField(max_length=100)
    def __str__(self):
        return self.name
        
import re
from django.db import models

# --- MOVE THIS TO THE TOP ---
def generate_pioneer_bom_id():
    from django.apps import apps

    BOMHeader = apps.get_model("accounts", "BOMHeader")
    max_num = 99
    for bom_id in BOMHeader.objects.values_list("bom_id", flat=True):
        match = re.search(r"(\d+)", bom_id or "")
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"BOM-{max_num + 1}"
# ============================================================

class BOMHeader(models.Model):
    STATUS_DRAFT = "DRAFT"
    STATUS_SENT_TO_GM = "SENT_TO_GM"
    STATUS_AWARDED = "AWARDED"
    STATUS_GENERATED = "GENERATED"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SENT_TO_GM, "Sent to GM"),
        (STATUS_AWARDED, "Awarded"),
        (STATUS_GENERATED, "Generated from RO"),
    ]

    bom_id = models.CharField(
        max_length=20,
        unique=True,
        default=generate_pioneer_bom_id,
        editable=False,
    )
    task = models.ForeignKey(
        "ProjectTask",
        on_delete=models.CASCADE,
        related_name="bom_headers",
    )
    ro = models.OneToOneField(
        "RequisitionOrder",
        on_delete=models.CASCADE,
        related_name="bom",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT
    )
    items_locked = models.BooleanField(
        default=False,
        help_text="Line items frozen after Snr Site Engineer locks the BOM list.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["task"], name="unique_bom_per_task"),
        ]

    def save(self, *args, **kwargs):
        if not (self.bom_id or "").strip():
            self.bom_id = generate_pioneer_bom_id()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.bom_id or f"BOM-{self.pk}"

# ==============================================================


class UserCategory(models.Model):
    code = models.CharField(
        max_length=40,
        unique=True,
        null=True,
        blank=True,
        help_text="Stable role key, e.g. SENIOR_SITE_MANAGER.",
    )
    description = models.CharField(max_length=100)
    rank = models.PositiveSmallIntegerField(
        default=0,
        help_text="Higher rank = more senior (used for display ordering).",
    )
    role_summary = models.TextField(
        blank=True,
        default="",
        help_text="Short summary of responsibilities for admin reference.",
    )
    modules = models.ManyToManyField(Module, blank=True)

    class Meta:
        ordering = ["-rank", "description"]

    def __str__(self):
        return self.description

class UserAccount(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    
    staff_no = models.CharField(max_length=20, unique=True, verbose_name="Employee Staff Number")
    
    # Added these for your requirement:
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    
    designation = models.CharField(max_length=100)
    contact_address = models.TextField()
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    
    # For Project Rights
    access_level = models.ForeignKey(UserCategory, on_delete=models.SET_NULL, null=True)
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_accounts",
        help_text="Client company this user belongs to (e.g. Pioneer, Company B).",
    )
    must_change_password = models.BooleanField(
        default=False,
        help_text="User must set password via onboarding link before full access.",
    )
    onboarded_at = models.DateTimeField(null=True, blank=True)
    onboarded_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="onboarded_users",
    )
    onboarding_email_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the onboarding set-password email was last sent successfully.",
    )
    onboarding_email_last_error = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Last onboarding email failure message, if any.",
    )
    control_gl_account = models.ForeignKey(
        "GLAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employee_controls",
        help_text="Employee advance control account for GM cash/M-Pesa disbursements.",
    )

    def onboarding_status_label(self):
        if not self.must_change_password:
            return "Active"
        if self.onboarding_email_last_error and not self.onboarding_email_sent_at:
            return "Email failed"
        if self.onboarding_email_sent_at:
            return "Awaiting password"
        return "Invite not sent"

    def __str__(self):
        return self.user.username


# ===============================
# 3b. SOFTWARE & CLIENT ORGANIZATION BRANDING
# ===============================
class AppSettings(models.Model):
    """Singleton record for Project Accounting software branding."""
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    app_name = models.CharField(max_length=120, default="Project Accounting")
    app_short_name = models.CharField(max_length=80, default="Project Accounting")
    app_tagline = models.CharField(
        max_length=200, blank=True, default="Financial Operations Platform"
    )
    support_email = models.EmailField(blank=True, default="")
    vendor_name = models.CharField(max_length=120, blank=True, default="")
    currency_code = models.CharField(
        max_length=10,
        default="USD",
        help_text="ISO-style code shown on reports (e.g. USD).",
    )
    currency_symbol = models.CharField(
        max_length=10,
        default="US$",
        help_text="Symbol or prefix shown before amounts (e.g. US$).",
    )

    class Meta:
        verbose_name = "Software settings"
        verbose_name_plural = "Software settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return self.app_name


class Organization(models.Model):
    """Client company on the Project Accounting platform (Pioneer, Company B, etc.)."""
    org_code = models.CharField(max_length=30, primary_key=True)
    name = models.CharField(
        max_length=200,
        help_text="Full legal name, e.g. Pioneer Contactors Co Ltd",
    )
    short_name = models.CharField(max_length=80)
    registered_address = models.TextField(
        blank=True,
        default="",
        help_text="Registered / postal address (optional).",
    )
    contact_address = models.TextField(
        blank=True,
        default="",
        help_text="Contact / office address shown on documents.",
    )
    phone = models.CharField(max_length=30, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    tax_pin = models.CharField(max_length=50, blank=True, default="")
    document_tagline = models.CharField(
        max_length=200, blank=True, default="Operations Command"
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Platform fallback when a user has no company assigned.",
    )

    class Meta:
        ordering = ["org_code"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            Organization.objects.exclude(pk=self.pk).update(is_default=False)
        elif not Organization.objects.filter(is_default=True).exists():
            self.is_default = True
            Organization.objects.filter(pk=self.pk).update(is_default=True)

    @classmethod
    def get_default(cls):
        return cls.objects.filter(is_default=True).first() or cls.objects.first()

    def __str__(self):
        return self.name


# ===============================
# 4. BANK ACCOUNTS
# ===============================
class BankAccount(models.Model):
    bank_account_id = models.CharField(max_length=50, primary_key=True)
    account_number = models.CharField(max_length=50)
    description = models.CharField(max_length=200)

    contact_address = models.TextField()
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    ledger_gl_account = models.ForeignKey(
        "GLAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bank_ledgers",
        help_text="Linked GL control account for this bank.",
    )

    def __str__(self):
        return f"{self.bank_account_id} - {self.description}"


# ===============================
# 5. SUPPLIER ACCOUNTS
# ===============================
class SupplierAccount(models.Model):
    supplier_id = models.CharField(max_length=50, primary_key=True)
    bank_account_number = models.CharField(max_length=50)
    description = models.CharField(max_length=200)

    contact_address = models.TextField()
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    control_gl_account = models.ForeignKey(
        "GLAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supplier_controls",
        help_text="Supplier sub-ledger control account for GM payments.",
    )

    def __str__(self):
        return f"{self.supplier_id} - {self.description}"


# ===============================
# 6. GL ANALYSIS CATEGORY
# ===============================
class GLAnalysisCategory(models.Model):
    category_id = models.CharField(max_length=50, primary_key=True)
    description = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.category_id} - {self.description}"


# ===============================
# 7. GENERAL LEDGER ACCOUNT
# ===============================
class GLAccount(models.Model):
    gl_account_id = models.CharField(max_length=50, primary_key=True)

    DEBIT_CREDIT_CHOICES = [
        ('DR', 'Debit'),
        ('CR', 'Credit')
    ]

    debit_credit = models.CharField(max_length=2, choices=DEBIT_CREDIT_CHOICES)
    description = models.CharField(max_length=200)

    analysis_category = models.ForeignKey(GLAnalysisCategory, on_delete=models.SET_NULL, null=True)

    ROLE_CEO_DISBURSEMENT = "CEO_DISBURSEMENT"
    ROLE_GM_OPERATING = "GM_OPERATING"
    ROLE_SUPPLIER_CONTROL = "SUPPLIER_CONTROL"
    ROLE_EMPLOYEE_CONTROL = "EMPLOYEE_CONTROL"
    ROLE_CHOICES = [
        (ROLE_CEO_DISBURSEMENT, "CEO Disbursement Account"),
        (ROLE_GM_OPERATING, "GM Operating / Expense Account"),
        (ROLE_SUPPLIER_CONTROL, "Supplier Control"),
        (ROLE_EMPLOYEE_CONTROL, "Employee Control"),
    ]
    account_role = models.CharField(
        max_length=30,
        choices=ROLE_CHOICES,
        blank=True,
        default="",
        help_text="System role for fund-control accounts.",
    )

    currency = models.CharField(max_length=10)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.gl_account_id} - {self.description}"


# ===============================
# 8. PROJECT TASK
# ===============================
class ProjectTask(models.Model):
    project_id = models.CharField(max_length=50, primary_key=True)
    description = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.project_id} - {self.description}"


# ===============================
# 9. PROJECT BUILD CATEGORY
# ===============================
class ProjectBuildCategory(models.Model):
    id = models.AutoField(primary_key=True)
    build_cat_id = models.CharField(max_length=50, unique=True)
    description = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.build_cat_id} - {self.description}"
        
# ===============================
# 9.5 PROJECT BUILDING
# ===============================
class ProjectBuilding(models.Model):
    id = models.AutoField(primary_key=True)
    building_code = models.CharField(max_length=50, unique=True)
    description = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.building_code} - {self.description}"
    

# ===============================
# 10. PRODUCT
# ===============================
class Product(models.Model):
    product_id = models.CharField(max_length=50, primary_key=True)
    description = models.CharField(max_length=200)

    unit_of_measure = models.CharField(max_length=20)
    stock_quantity = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.product_id} - {self.description}"
        
# =====================================
class RequisitionOrder(models.Model):
    ro_no = models.CharField(max_length=50, unique=True)
    task = models.ForeignKey(ProjectTask, on_delete=models.CASCADE, related_name="ros")
    created_by = models.ForeignKey(UserAccount, on_delete=models.SET_NULL, null=True)

    date_raised = models.DateTimeField(auto_now_add=True)
    technical_requirement_note = models.TextField(blank=True, null=True)

    status = models.CharField(
        max_length=20,
        choices=[
            ("DRAFT", "Draft"),
            ("SUBMITTED", "Submitted"),
            ("SIGNED", "Signed"),
        ],
        default="DRAFT"
    )

    def __str__(self):
        return self.ro_no

    class Meta:
        indexes = [
            models.Index(fields=["ro_no"]),
            models.Index(fields=["task"]),
        ]


class RequisitionOrderItem(models.Model):
    ro = models.ForeignKey(RequisitionOrder, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)

    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )

    uom = models.CharField(max_length=20)
    tech_spec_summary = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.ro.ro_no} - Item {self.id}"
        
# ===============================
# 11. BOM & REQUISITION (Transaction)
# ===============================
class BOMTransaction(models.Model):
    """The 'Wish List' for a specific Task"""
    project_task = models.ForeignKey(ProjectTask, on_delete=models.PROTECT)
    build_category = models.ForeignKey(ProjectBuildCategory, on_delete=models.PROTECT)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    
    quantity_required = models.DecimalField(max_digits=12, decimal_places=2)
    date_raised = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default='PENDING') # PENDING, RFQ, LPO

# ===============================
# 12. RFQ & QUOTATION (Transaction)
# ===============================
# C:\project_accounting\accounts\models.py

class RFQTransaction(models.Model):
    rfq_no = models.CharField(max_length=50, unique=True)
    bom_item = models.ForeignKey(BOMTransaction, on_delete=models.CASCADE)
    supplier = models.ForeignKey(SupplierAccount, on_delete=models.PROTECT)
    
    quote_ref = models.CharField(max_length=100, blank=True)
    unit_cost_quoted = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    
    # Updated: null=True allows you to save the RFQ without a file initially
    supporting_document = models.FileField(
        upload_to='quotes/%Y/%m/', 
        null=True, 
        blank=True,
        help_text="Upload winning quote PDF for UN audit compliance"
    )
    
    is_selected = models.BooleanField(default=False)
    
from django.db import models
from django.contrib.auth.models import User

# ===============================
# 13. LPO & GRN (With Project DNA)
# ===============================
from django.utils import timezone

class LPOTransaction(models.Model):
    # --- PROJECT DNA (Existing Core) ---
    lpo_no = models.CharField(max_length=50, unique=True, editable=False)
    # selected_quote = models.OneToOneField('RFQTransaction', on_delete=models.PROTECT)
    # ❌ REMOVE THIS COUPLING (causing your errors)
    # selected_quote = models.OneToOneField('RFQTransaction', on_delete=models.PROTECT)

    # ✅ REPLACE WITH SUPPLIER + SOURCE TRACEABILITY
    supplier = models.ForeignKey(
        'SupplierAccount',
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )
    
    project_task = models.ForeignKey('ProjectTask', on_delete=models.PROTECT)
    
    # building = models.ForeignKey('ProjectBuilding', on_delete=models.PROTECT)
    # build_category = models.ForeignKey('ProjectBuildCategory', on_delete=models.PROTECT)
    building = models.ForeignKey(
        'ProjectBuilding',
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )

    build_category = models.ForeignKey(
        'ProjectBuildCategory',
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )
    
    # --- AUDIT & EVALUATION (Existing Core) ---
    date_issued = models.DateTimeField(auto_now_add=True)
    variance_explanation = models.TextField(blank=True, help_text="Required if quote is not the lowest")
    stars = models.IntegerField(default=0)
    
    # --- NEW OPERATIONAL FEATURES ---
    supplier_contact = models.CharField(max_length=255, null=True, blank=True)
    awarded_by_office = models.CharField(max_length=255, default="Main Office")
    delivery_deadline = models.DateField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    STATUS_ACTIVE = "ACTIVE"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_CANCELLED, "Cancelled"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # --- UNIQUE SERIAL GENERATOR ---
    def save(self, *args, **kwargs):
        if not self.lpo_no:
            year = timezone.now().year
            last = LPOTransaction.objects.filter(lpo_no__startswith=f"LPQ-{year}-").order_by('-lpo_no').first()
            seq = int(last.lpo_no.split('-')[-1]) + 1 if last else 1
            self.lpo_no = f"LPQ-{year}-{seq:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.lpo_no} | {self.project_task.description}"
# ============================================================================

class LPOItem(models.Model):
    lpo = models.ForeignKey(
        LPOTransaction, 
        on_delete=models.CASCADE, 
        related_name='items'
    )
    
    # Allow manual entry or null if no RFQ exists
    rfq_no = models.CharField(max_length=50, null=True, blank=True)
    
    description = models.CharField(max_length=255)
    uom = models.CharField(max_length=50)
    qty = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    total_price = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.lpo.lpo_no} | {self.description}"

# ============================================================================

class GRNTransaction(models.Model):
    grn_no = models.CharField(max_length=50, unique=True, editable=False)
    lpo = models.ForeignKey(LPOTransaction, on_delete=models.PROTECT, related_name="grns")

    delivery_note_ref = models.CharField(max_length=100, blank=True, default="")
    invoice_ref = models.CharField(max_length=100, blank=True, default="")
    qty_received = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    receipt_date = models.DateField(default=timezone.now)
    date_received = models.DateTimeField(auto_now_add=True)
    received_by = models.ForeignKey(User, on_delete=models.PROTECT)
    received_by_name = models.CharField(max_length=255, blank=True, default="")
    supplier_rep_name = models.CharField(max_length=255, blank=True, default="")

    def save(self, *args, **kwargs):
        if not self.grn_no:
            year = timezone.now().year
            last = (
                GRNTransaction.objects.filter(grn_no__startswith=f"GRN-{year}-")
                .order_by("-grn_no")
                .first()
            )
            seq = int(last.grn_no.split("-")[-1]) + 1 if last else 1
            self.grn_no = f"GRN-{year}-{seq:04d}"
        super().save(*args, **kwargs)

    @property
    def is_partial(self):
        for line in self.lpo.items.all():
            ordered = line.qty
            received = (
                GRNItem.objects.filter(lpo_item=line).aggregate(
                    total=models.Sum("qty_received")
                )["total"]
                or Decimal("0")
            )
            if received < ordered:
                return True
        return False

    def __str__(self):
        return f"{self.grn_no} | {self.lpo.lpo_no}"


class GRNItem(models.Model):
    grn = models.ForeignKey(GRNTransaction, on_delete=models.CASCADE, related_name="lines")
    lpo_item = models.ForeignKey(LPOItem, on_delete=models.PROTECT, related_name="grn_lines")
    qty_received = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        unique_together = [["grn", "lpo_item"]]

    def __str__(self):
        return f"{self.grn.grn_no} | {self.lpo_item.description} × {self.qty_received}"

# ===============================
# 14. PAYMENT ORDER (The Money Exit)
# ===============================
class PaymentOrder(models.Model):
    """Payment input voucher raised against a GRN (invoice-backed)."""
    pay_order_no = models.CharField(max_length=50, unique=True, editable=False)
    grn = models.OneToOneField(
        GRNTransaction, on_delete=models.PROTECT, related_name="payment_voucher"
    )

    PAY_METHODS = [
        ("BANK", "Bank Transfer"),
        ("CHQ", "Cheque"),
        ("CASH", "Cash"),
        ("MPESA", "M-Pesa"),
    ]
    payment_method = models.CharField(max_length=10, choices=PAY_METHODS)
    source_bank = models.ForeignKey("BankAccount", on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    transfer_reference = models.CharField(max_length=100, blank=True, default="")
    cheque_number = models.CharField(max_length=100, blank=True, default="")
    payment_notes = models.TextField(blank=True, default="")
    prepared_by_name = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    is_confirmed_by_director = models.BooleanField(default=False)
    date_confirmed = models.DateTimeField(null=True, blank=True)
    ledger_posting = models.ForeignKey(
        "GLLedgerPosting",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_orders",
    )

    def save(self, *args, **kwargs):
        if not self.pay_order_no:
            year = timezone.now().year
            last = (
                PaymentOrder.objects.filter(pay_order_no__startswith=f"PV-{year}-")
                .order_by("-pay_order_no")
                .first()
            )
            seq = int(last.pay_order_no.split("-")[-1]) + 1 if last else 1
            self.pay_order_no = f"PV-{year}-{seq:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.pay_order_no} | {self.grn.grn_no}"
    
    
class ProjectTaskBudget_actuals(models.Model):
    # ... existing fields (id, description, building, category) ...

    def get_budgeted_amount(self):
        """Pulls the frozen baseline created during RFQ selection"""
        from .models import TaskBudgetLineItem
        return TaskBudgetLineItem.objects.filter(budget__project_task=self).aggregate(
            total=models.Sum('total_price'))['total'] or 0

    def get_actual_spent(self):
        """Calculates money paid out via Confirmed Payment Orders"""
        return PaymentOrder.objects.filter(
            grn__lpo__project_task=self, 
            is_confirmed_by_director=True
        ).aggregate(total=models.Sum('grn__lpo__selected_quote__unit_cost_quoted'))['total'] or 0

    def get_outstanding_commitment(self):
        """LPOs issued but not yet paid (Money promised)"""
        return LPOTransaction.objects.filter(project_task=self).exclude(
            id__in=PaymentOrder.objects.values_list('grn__lpo_id', flat=True)
        ).aggregate(total=models.Sum('selected_quote__unit_cost_quoted'))['total'] or 0
        
        
 #===============================================================================
 
# 3. THE ITEM (Third - Now it can see BOMHeader)
class BOMItem(models.Model):
    # Change BOMHeader to 'BOMHeader' (with quotes)
    header = models.ForeignKey('BOMHeader', related_name='items', on_delete=models.CASCADE)
    pillar_id = models.IntegerField() 
    description = models.CharField(max_length=255)
    qty = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    uom = models.CharField(max_length=50)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    

    
    
class MiscRequisitionOrder(models.Model):
    # Core Identity
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mro_number = models.CharField(max_length=50, unique=True, null=True, blank=True)
    task = models.ForeignKey('ProjectTask', on_delete=models.PROTECT, related_name='misc_requisitions')
    source_mpo = models.OneToOneField(
        'MiscPurchaseOrder',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='committed_mro',
    )
    
    # Operational State
    is_sourcing = models.BooleanField(default=True)
    funding_status = models.CharField(
        max_length=20, 
        choices=[('PENDING', 'Pending'), ('LOCKED', 'Locked'), ('DISBURSED', 'Disbursed'), ('RECONCILED', 'Reconciled')],
        default='PENDING'
    )
    
    # Accountability & Financials
    messenger_name = models.CharField(max_length=100, default="Mr. Omambo")
    authorized_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.mro_number or 'MRO-' + str(self.id)[:8]}"

# ========================================================================
# accounts/models.py

class MPOStatusRegistry(models.Model):
    # Rename 'mro' to 'mro_record' to avoid the naming conflict with Python's internal .mro() method
    mro_record = models.OneToOneField(
        'MiscRequisitionOrder', 
        on_delete=models.CASCADE, 
        primary_key=True, 
        related_name='status_registry'
    )
    
    is_sourcing = models.BooleanField(default=False)
    funding_status = models.CharField(max_length=20) 
    task_code = models.CharField(max_length=50) 
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['is_sourcing', 'funding_status', 'task_code']),
        ]
# ===================================================================================

# accounts/models.py

import uuid
from django.db import models
from django.utils import timezone

class MiscPurchaseOrder(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey('ProjectTask', on_delete=models.PROTECT)
    
    # State Machine
    is_sourcing = models.BooleanField(default=False)
    funding_status = models.CharField(
        max_length=20,
        choices=[
            ('PENDING', 'Pending'),
            ('SUBMITTED', 'Submitted'),
            ('LOCKED', 'Locked'),
            ('DISBURSED', 'Disbursed'),
        ],
        default='PENDING',
    )
    
    mpo_number = models.CharField(max_length=50, unique=True, null=True, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    # Audit
    messenger_name = models.CharField(max_length=100, default="Mr. Omambo")
    created_at = models.DateTimeField(auto_now_add=True)

class MiscPurchaseItem(models.Model):
    mpo = models.ForeignKey(MiscPurchaseOrder, on_delete=models.CASCADE, related_name='items')
    task = models.ForeignKey('ProjectTask', on_delete=models.PROTECT)
    gl_expense_account = models.ForeignKey('GLAccount', on_delete=models.PROTECT)
    
    description = models.CharField(max_length=255)
    uom = models.CharField(max_length=50, default="EA")
    qty = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)


# ================================================================
class CashClearingRecord(models.Model):
    # Linkage to the MPO being cleared
    mpo = models.OneToOneField('MiscPurchaseOrder', on_delete=models.PROTECT, related_name='clearing_record')
    
    # Financial Details
    amount_cleared = models.DecimalField(max_digits=12, decimal_places=2)
    disbursement_method = models.CharField(max_length=20, choices=[
        ('CASH', 'Cash'), ('CHEQUE', 'Cheque'), ('MPESA', 'M-Pesa'), ('OTHER', 'Other')
    ])
    other_method_details = models.CharField(max_length=255, blank=True, null=True)
    
    # Accountability
    authorized_by = models.ForeignKey('auth.User', on_delete=models.PROTECT, related_name='authorized_clearing')
    gl_account = models.ForeignKey('GLAccount', on_delete=models.PROTECT)
    
    # Audit trail
    payment_description = models.TextField(help_text="Details of the payment/transaction")
    cleared_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Clearance for {self.mpo.mpo_number} - {self.amount_cleared}"


class AdHocOfficerPaymentVoucher(models.Model):
    """Officer payment voucher for partial ad-hoc RO purchases (cash / M-Pesa)."""
    voucher_no = models.CharField(max_length=50, unique=True, editable=False)
    mpo = models.ForeignKey(
        "MiscPurchaseOrder", on_delete=models.PROTECT, related_name="officer_vouchers"
    )
    task = models.ForeignKey("ProjectTask", on_delete=models.PROTECT)
    officer_name = models.CharField(max_length=255, help_text="Receiving / purchasing officer")
    employee = models.ForeignKey(
        "UserAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="officer_vouchers",
        help_text="Linked employee registry record for control-account posting.",
    )
    PAY_METHODS = [
        ("CASH", "Cash"),
        ("MPESA", "M-Pesa"),
    ]
    payment_method = models.CharField(max_length=10, choices=PAY_METHODS)
    mpesa_reference = models.CharField(max_length=100, blank=True, default="")
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gm_authority_name = models.CharField(max_length=255, blank=True, default="")
    prepared_by_name = models.CharField(max_length=255, blank=True, default="")
    payment_notes = models.TextField(blank=True, default="")
    actual_spent = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    change_returned = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    purchase_receipt_ref = models.CharField(max_length=100, blank=True, default="")
    settled_by_name = models.CharField(max_length=255, blank=True, default="")
    settled_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(default=timezone.now)
    ledger_posting = models.ForeignKey(
        "GLLedgerPosting",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="officer_vouchers",
    )

    @property
    def is_settled(self):
        return self.settled_at is not None

    def save(self, *args, **kwargs):
        if not self.voucher_no:
            year = timezone.now().year
            last = (
                AdHocOfficerPaymentVoucher.objects.filter(
                    voucher_no__startswith=f"OPV-{year}-"
                )
                .order_by("-voucher_no")
                .first()
            )
            seq = int(last.voucher_no.split("-")[-1]) + 1 if last else 1
            self.voucher_no = f"OPV-{year}-{seq:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.voucher_no} | {self.mpo.mpo_number} | {self.officer_name}"


class AdHocOfficerPaymentVoucherLine(models.Model):
    voucher = models.ForeignKey(
        AdHocOfficerPaymentVoucher, on_delete=models.CASCADE, related_name="lines"
    )
    mpo_item = models.ForeignKey(
        "MiscPurchaseItem", on_delete=models.PROTECT, related_name="officer_purchase_lines"
    )
    line_no = models.PositiveSmallIntegerField(default=0)
    qty_purchased = models.DecimalField(max_digits=10, decimal_places=2)
    qty_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.mpo_item.description} × {self.qty_purchased}"


# ==============================================================================


class ProjectBudget(models.Model):
    BUDGET_RFQ_LPO = "RFQ_LPO"
    BUDGET_ADHOC_MISC = "ADHOC_MISC"
    BUDGET_TYPE_CHOICES = [
        (BUDGET_RFQ_LPO, "Project Budget (RFQ_LPO)"),
        (BUDGET_ADHOC_MISC, "Ad-Hoc Budget (ADHOC_MISC)"),
    ]

    # Optional field: If NULL, this is an Admin/Overhead budget.
    # If set, it's a project-specific budget.
    task = models.OneToOneField(
        'ProjectTask', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='budget'
    )

    # One task = one budget channel (RFQ_LPO or ADHOC_MISC) — never both.
    budget_type = models.CharField(
        max_length=20,
        choices=BUDGET_TYPE_CHOICES,
        default=BUDGET_RFQ_LPO,
        blank=True,
    )
    
    # Identifier for tracking (e.g., 'PROJECT-001' or 'ADMIN-Q2')
    budget_label = models.CharField(max_length=100)
    
    # Financial components
    material_total_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0) 
    labour_burden = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    misc_reserve = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    equipment_reserve = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        help_text="Equipment hire or purchase allocation",
    )
    
    # The final authorized ceiling
    total_authorized_budget = models.DecimalField(max_digits=15, decimal_places=2)
    
    # Audit tracking
    created_at = models.DateTimeField(auto_now_add=True)
    version = models.IntegerField(default=1)
    is_ceo_approved = models.BooleanField(
        default=False,
        help_text="CEO AIE lock — line figures read-only after approval",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="ceo_approved_budgets",
    )
    ceo_aie_reference = models.CharField(max_length=100, blank=True, default="")

    REVIEW_PROVISION = "PROVISION"
    REVIEW_WITH_CEO = "WITH_CEO"
    REVIEW_RETURNED = "RETURNED"
    REVIEW_APPROVED = "APPROVED"
    REVIEW_RELEASED = "RELEASED"
    REVIEW_STATUS_CHOICES = [
        (REVIEW_PROVISION, "Provisional — not sent to CEO"),
        (REVIEW_WITH_CEO, "With CEO — awaiting confirmation"),
        (REVIEW_RETURNED, "Returned to GM for correction"),
        (REVIEW_APPROVED, "CEO confirmed (AIE locked)"),
        (REVIEW_RELEASED, "Funds released to GM"),
    ]
    review_status = models.CharField(
        max_length=20,
        choices=REVIEW_STATUS_CHOICES,
        default=REVIEW_PROVISION,
        blank=True,
    )
    last_return_reason = models.TextField(
        blank=True,
        default="",
        help_text="Latest CEO reason when budget was returned to GM.",
    )

    @property
    def is_locked(self):
        return self.is_ceo_approved

    def __str__(self):
        return f"{self.budget_label} - KES {self.total_authorized_budget}"


class BudgetReviewEvent(models.Model):
    """GM ↔ CEO budget confirmation thread — memos, returns, approvals."""

    ACTION_GM_SUBMIT = "GM_SUBMIT"
    ACTION_GM_RESUBMIT = "GM_RESUBMIT"
    ACTION_GM_REMIND = "GM_REMIND"
    ACTION_CEO_RETURN = "CEO_RETURN"
    ACTION_CEO_APPROVE = "CEO_APPROVE"
    ACTION_CEO_RELEASE = "CEO_RELEASE"
    ACTION_CHOICES = [
        (ACTION_GM_SUBMIT, "GM submitted budget to CEO"),
        (ACTION_GM_RESUBMIT, "GM resubmitted after CEO return"),
        (ACTION_GM_REMIND, "GM sent CEO budget approval reminder (desk on hold)"),
        (ACTION_CEO_RETURN, "CEO returned budget to GM"),
        (ACTION_CEO_APPROVE, "CEO approved and locked budget (AIE)"),
        (ACTION_CEO_RELEASE, "CEO released funds to GM"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    budget = models.ForeignKey(
        ProjectBudget, on_delete=models.CASCADE, related_name="review_events"
    )
    task = models.ForeignKey(
        "ProjectTask", on_delete=models.PROTECT, related_name="budget_review_events"
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    memo_subject = models.CharField(max_length=200, blank=True, default="")
    memo_body = models.TextField(blank=True, default="")
    reason = models.TextField(blank=True, default="")
    from_officer = models.CharField(max_length=200, blank=True, default="")
    to_officer = models.CharField(max_length=200, blank=True, default="")
    source_mpo = models.ForeignKey(
        "MiscPurchaseOrder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="budget_review_events",
    )
    source_mro = models.ForeignKey(
        "MiscRequisitionOrder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="budget_review_events",
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="budget_review_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.get_action_display()} — {self.task_id} @ {self.created_at:%Y-%m-%d}"

#=================================================================

class BudgetTransaction(models.Model):
    # Link back to the budget (which is linked to the task)
    budget = models.ForeignKey(ProjectBudget, on_delete=models.CASCADE, related_name='transactions')
    
    # Category enforcement to keep your accounts clean
    CATEGORY_CHOICES = [
        ('MATERIAL', 'Material Total Cost'),
        ('LABOUR', 'Labour Burden'),
        ('MISC', 'Misc / Logistics Reserve'),
        ('MAINTENANCE', 'Office Maintenance & Ops'),
        ('EQUIPMENT', 'Equipment Hire / Purchase'),
    ]
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    description = models.CharField(max_length=255) # e.g., "Bamburi Cement - MRO 101"
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.category}: KES {self.amount} for {self.budget.budget_label}"
        
# ====================================================================

class TaskDisbursementPayment(models.Model):
    """GM AIE payment posted against a project task budget line."""

    LINE_MATERIAL = "MATERIAL"
    LINE_MAINTENANCE = "MAINTENANCE"
    LINE_LABOUR = "LABOUR"
    LINE_EQUIPMENT = "EQUIPMENT"
    BUDGET_LINE_CHOICES = [
        (LINE_MATERIAL, "Payment of Goods"),
        (LINE_MAINTENANCE, "Office Maintenance & Ops"),
        (LINE_LABOUR, "Labour"),
        (LINE_EQUIPMENT, "Equipment Hire / Purchase"),
    ]
    PAY_METHODS = [
        ("CASH", "Cash"),
        ("BANK", "Bank Transfer"),
        ("CHQ", "Cheque"),
        ("MPESA", "M-Pesa"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment_number = models.CharField(max_length=50, unique=True)
    task = models.ForeignKey(
        ProjectTask, on_delete=models.PROTECT, related_name="disbursement_payments"
    )
    budget_line = models.CharField(max_length=20, choices=BUDGET_LINE_CHOICES)
    description = models.CharField(max_length=255)
    payee = models.CharField(max_length=200, blank=True, default="")
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_method = models.CharField(max_length=10, choices=PAY_METHODS, default="BANK")
    aie_reference = models.CharField(
        max_length=100, blank=True, default="",
        help_text="CEO AIE authority reference",
    )
    posted_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.payment_number} — {self.get_budget_line_display()} KES {self.amount}"


class CEOFundRelease(models.Model):
    """CEO AIE holder releases authorized funds to GM Accounting via bank transfer."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    release_number = models.CharField(max_length=50, unique=True)
    task = models.ForeignKey(
        ProjectTask, on_delete=models.PROTECT, related_name="fund_releases"
    )
    budget = models.ForeignKey(
        ProjectBudget, on_delete=models.PROTECT, related_name="fund_releases"
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    transfer_method = models.CharField(max_length=20, default="BANK")
    from_office = models.CharField(
        max_length=200, default="CEO Office — Authority to Incur Expenditure (AIE)"
    )
    to_officer = models.CharField(
        max_length=200, default="GM — Accounting Officer"
    )
    bank_reference = models.CharField(max_length=100, blank=True, default="")
    aie_memo_ref = models.CharField(max_length=100, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    authorized_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="ceo_fund_releases",
    )
    released_at = models.DateTimeField(auto_now_add=True)
    ledger_posting = models.ForeignKey(
        "GLLedgerPosting",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fund_releases",
    )

    class Meta:
        ordering = ["-released_at"]

    def __str__(self):
        return f"{self.release_number} — KES {self.amount} → {self.to_officer}"


class LedgerControlSettings(models.Model):
    """Singleton mapping for CEO → GM fund-control GL and bank accounts."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    ceo_disbursement_gl = models.ForeignKey(
        GLAccount,
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    ceo_disbursement_bank = models.ForeignKey(
        BankAccount,
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    gm_operating_gl = models.ForeignKey(
        GLAccount,
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    gm_operating_bank = models.ForeignKey(
        BankAccount,
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Ledger control settings"
        verbose_name_plural = "Ledger control settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class GLLedgerPosting(models.Model):
    """Immutable GL movement for CEO disbursement and GM payments."""

    TYPE_CEO_TO_GM = "CEO_TO_GM"
    TYPE_OFFICER_ADVANCE = "OFFICER_ADVANCE"
    TYPE_SUPPLIER_PAYMENT = "SUPPLIER_PAYMENT"
    TYPE_GM_EXPENSE = "GM_EXPENSE"
    TYPE_CHOICES = [
        (TYPE_CEO_TO_GM, "CEO to GM transfer"),
        (TYPE_OFFICER_ADVANCE, "Employee advance"),
        (TYPE_SUPPLIER_PAYMENT, "Supplier payment"),
        (TYPE_GM_EXPENSE, "GM expense payment"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(
        ProjectTask, on_delete=models.PROTECT, null=True, blank=True, related_name="ledger_postings"
    )
    posting_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    debit_gl = models.ForeignKey(
        GLAccount, on_delete=models.PROTECT, related_name="ledger_debits"
    )
    credit_gl = models.ForeignKey(
        GLAccount, on_delete=models.PROTECT, related_name="ledger_credits"
    )
    reference_type = models.CharField(max_length=50, blank=True, default="")
    reference_id = models.CharField(max_length=100, blank=True, default="")
    memo = models.TextField(blank=True, default="")
    posted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="ledger_postings"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.posting_type} {self.amount} ({self.reference_type}:{self.reference_id})"


# ====================================================================


        
        
        
