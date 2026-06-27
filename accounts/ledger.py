"""Fund-control GL posting — CEO disbursement account -> GM operating account."""

from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum

from accounts.models import (
    AdHocOfficerPaymentVoucher,
    CEOFundRelease,
    GLAccount,
    GLLedgerPosting,
    LedgerControlSettings,
    PaymentOrder,
    ProjectBudget,
    SupplierAccount,
    TaskDisbursementPayment,
    UserAccount,
)


def _money(val):
    return Decimal(str(val or "0")).quantize(Decimal("0.01"))


def get_ledger_settings():
    return LedgerControlSettings.get()


def ensure_fund_control_accounts(currency="USD"):
    """Create CEO / GM control GL and bank accounts if missing."""
    settings = get_ledger_settings()
    changed = []

    if not settings.ceo_disbursement_gl_id:
        gl, _ = GLAccount.objects.get_or_create(
            gl_account_id="GL-CEO-DISB",
            defaults={
                "debit_credit": "DR",
                "description": "CEO Disbursement Account",
                "currency": currency,
                "amount": Decimal("0.00"),
                "account_role": GLAccount.ROLE_CEO_DISBURSEMENT,
            },
        )
        settings.ceo_disbursement_gl = gl
        changed.append("ceo_disbursement_gl")

    if not settings.gm_operating_gl_id:
        gl, _ = GLAccount.objects.get_or_create(
            gl_account_id="GL-GM-OPS",
            defaults={
                "debit_credit": "DR",
                "description": "GM Operating / Expense Account",
                "currency": currency,
                "amount": Decimal("0.00"),
                "account_role": GLAccount.ROLE_GM_OPERATING,
            },
        )
        settings.gm_operating_gl = gl
        changed.append("gm_operating_gl")

    from accounts.models import BankAccount

    if not settings.ceo_disbursement_bank_id:
        bank, _ = BankAccount.objects.get_or_create(
            bank_account_id="BANK-CEO-DISB",
            defaults={
                "account_number": "CEO-DISB-001",
                "description": "CEO Disbursement Bank Account",
                "contact_address": "CEO Office",
                "phone": "0000000000",
                "email": "ceo@pioneer.local",
                "ledger_gl_account": settings.ceo_disbursement_gl,
            },
        )
        if bank.ledger_gl_account_id != settings.ceo_disbursement_gl_id:
            bank.ledger_gl_account = settings.ceo_disbursement_gl
            bank.save(update_fields=["ledger_gl_account"])
        settings.ceo_disbursement_bank = bank
        changed.append("ceo_disbursement_bank")

    if not settings.gm_operating_bank_id:
        bank, _ = BankAccount.objects.get_or_create(
            bank_account_id="BANK-GM-OPS",
            defaults={
                "account_number": "GM-OPS-001",
                "description": "GM Operating / Expense Bank Account",
                "contact_address": "GM Accounting Office",
                "phone": "0000000000",
                "email": "gm@pioneer.local",
                "ledger_gl_account": settings.gm_operating_gl,
            },
        )
        if bank.ledger_gl_account_id != settings.gm_operating_gl_id:
            bank.ledger_gl_account = settings.gm_operating_gl
            bank.save(update_fields=["ledger_gl_account"])
        settings.gm_operating_bank = bank
        changed.append("gm_operating_bank")

    if changed:
        settings.save(update_fields=changed)
    return settings


def ensure_treasury_gl(currency="USD"):
    gl, _ = GLAccount.objects.get_or_create(
        gl_account_id="GL-TREASURY",
        defaults={
            "debit_credit": "DR",
            "description": "Treasury / opening balance contra",
            "currency": currency,
            "amount": Decimal("0.00"),
            "account_role": "",
        },
    )
    return gl


def ensure_supplier_control_gl(supplier):
    if supplier.control_gl_account_id:
        return supplier.control_gl_account
    gl_id = f"GL-SUP-{supplier.supplier_id}"[:50]
    gl, _ = GLAccount.objects.get_or_create(
        gl_account_id=gl_id,
        defaults={
            "debit_credit": "CR",
            "description": f"Supplier control — {supplier.description}"[:200],
            "currency": "USD",
            "amount": Decimal("0.00"),
            "account_role": GLAccount.ROLE_SUPPLIER_CONTROL,
        },
    )
    supplier.control_gl_account = gl
    supplier.save(update_fields=["control_gl_account"])
    return gl


def ensure_employee_control_gl(user_account):
    if user_account.control_gl_account_id:
        return user_account.control_gl_account
    gl_id = f"GL-EMP-{user_account.staff_no}"[:50]
    name = f"{user_account.first_name} {user_account.last_name}".strip() or user_account.staff_no
    gl, _ = GLAccount.objects.get_or_create(
        gl_account_id=gl_id,
        defaults={
            "debit_credit": "DR",
            "description": f"Employee control — {name}"[:200],
            "currency": "USD",
            "amount": Decimal("0.00"),
            "account_role": GLAccount.ROLE_EMPLOYEE_CONTROL,
        },
    )
    user_account.control_gl_account = gl
    user_account.save(update_fields=["control_gl_account"])
    return gl


def resolve_employee_for_officer_name(name):
    name = (name or "").strip()
    if not name:
        return None
    for ua in UserAccount.objects.select_related("control_gl_account"):
        full = f"{ua.first_name} {ua.last_name}".strip()
        if full and full.lower() == name.lower():
            return ua
        if ua.staff_no and ua.staff_no.lower() == name.lower():
            return ua
    return None


def _adjust_gl_balance(gl, delta):
    GLAccount.objects.filter(pk=gl.pk).update(amount=F("amount") + delta)


def task_gm_wallet_balance(task):
    """CEO-released funds for this task minus GM outflows."""
    if not task:
        return Decimal("0.00")
    released = (
        CEOFundRelease.objects.filter(task=task).aggregate(t=Sum("amount"))["t"]
        or Decimal("0.00")
    )
    officer = (
        AdHocOfficerPaymentVoucher.objects.filter(task=task).aggregate(t=Sum("amount"))["t"]
        or Decimal("0.00")
    )
    supplier = (
        PaymentOrder.objects.filter(grn__lpo__project_task=task).aggregate(t=Sum("amount"))["t"]
        or Decimal("0.00")
    )
    generic = (
        TaskDisbursementPayment.objects.filter(task=task).aggregate(t=Sum("amount"))["t"]
        or Decimal("0.00")
    )
    return _money(released - officer - supplier - generic)


def gm_operating_gl_balance():
    settings = ensure_fund_control_accounts()
    gl = settings.gm_operating_gl
    if not gl:
        return Decimal("0.00")
    gl.refresh_from_db()
    return _money(gl.amount)


def _ceo_gate_allows(task):
    budget = ProjectBudget.objects.filter(task=task).first()
    approved = bool(budget and budget.is_ceo_approved)
    released = CEOFundRelease.objects.filter(task=task).exists()
    return approved and released


def _post_entry(
    *,
    task,
    posting_type,
    amount,
    debit_gl,
    credit_gl,
    reference_type,
    reference_id,
    memo,
    user,
):
    amount = _money(amount)
    if amount <= 0:
        raise ValueError("Posting amount must be greater than zero.")
    with transaction.atomic():
        posting = GLLedgerPosting.objects.create(
            task=task,
            posting_type=posting_type,
            amount=amount,
            debit_gl=debit_gl,
            credit_gl=credit_gl,
            reference_type=reference_type,
            reference_id=str(reference_id),
            memo=memo,
            posted_by=user,
        )
        _adjust_gl_balance(debit_gl, amount)
        _adjust_gl_balance(credit_gl, -amount)
        return posting


def fund_ceo_disbursement_account(amount, user, *, memo="Treasury funding of CEO disbursement account"):
    settings = ensure_fund_control_accounts()
    ceo_gl = settings.ceo_disbursement_gl
    treasury_gl = ensure_treasury_gl()
    amount = _money(amount)
    if amount <= 0:
        raise ValueError("Amount must be positive.")
    treasury_gl.refresh_from_db()
    if treasury_gl.amount < amount:
        GLAccount.objects.filter(pk=treasury_gl.pk).update(amount=F("amount") + amount)
        treasury_gl.refresh_from_db()
    return _post_entry(
        task=None,
        posting_type=GLLedgerPosting.TYPE_CEO_TO_GM,
        amount=amount,
        debit_gl=ceo_gl,
        credit_gl=treasury_gl,
        reference_type="ceo_funding",
        reference_id="treasury",
        memo=memo,
        user=user,
    )


def post_ceo_fund_release(release, user):
    settings = ensure_fund_control_accounts()
    ceo_gl = settings.ceo_disbursement_gl
    gm_gl = settings.gm_operating_gl
    if not ceo_gl or not gm_gl:
        raise ValueError("Fund control GL accounts are not configured.")

    amount = _money(release.amount)
    ceo_gl.refresh_from_db()
    if ceo_gl.amount < amount:
        raise ValueError(
            f"Insufficient balance in CEO Disbursement Account "
            f"(available {ceo_gl.amount:.2f}, required {amount:.2f})."
        )

    posting = _post_entry(
        task=release.task,
        posting_type=GLLedgerPosting.TYPE_CEO_TO_GM,
        amount=amount,
        debit_gl=gm_gl,
        credit_gl=ceo_gl,
        reference_type="ceo_fund_release",
        reference_id=release.release_number,
        memo=f"CEO fund release {release.release_number} -> GM Operating",
        user=user,
    )
    release.ledger_posting = posting
    release.save(update_fields=["ledger_posting"])
    return posting


def assert_task_can_disburse(task, amount, *, require_ceo_gate=True):
    amount = _money(amount)
    if require_ceo_gate and not _ceo_gate_allows(task):
        raise ValueError(
            "CEO budget approval and fund release required before GM can pay."
        )

    wallet = task_gm_wallet_balance(task)
    if amount > wallet:
        raise ValueError(
            f"Insufficient CEO-released funds for task {task.project_id}. "
            f"Available {wallet:.2f}, requested {amount:.2f}."
        )

    gm_balance = gm_operating_gl_balance()
    if amount > gm_balance:
        raise ValueError(
            f"Insufficient balance in GM Operating Account "
            f"(available {gm_balance:.2f}, requested {amount:.2f})."
        )


def post_officer_advance_voucher(voucher, user, employee=None):
    settings = ensure_fund_control_accounts()
    gm_gl = settings.gm_operating_gl
    employee = employee or voucher.employee or resolve_employee_for_officer_name(voucher.officer_name)
    if employee and not voucher.employee_id:
        voucher.employee = employee
        voucher.save(update_fields=["employee"])
    if employee:
        emp_gl = ensure_employee_control_gl(employee)
    else:
        emp_gl, _ = GLAccount.objects.get_or_create(
            gl_account_id="GL-EMP-MISC",
            defaults={
                "debit_credit": "DR",
                "description": "Employee control — unregistered officers",
                "currency": "USD",
                "amount": Decimal("0.00"),
                "account_role": GLAccount.ROLE_EMPLOYEE_CONTROL,
            },
        )

    assert_task_can_disburse(voucher.task, voucher.amount, require_ceo_gate=True)

    posting = _post_entry(
        task=voucher.task,
        posting_type=GLLedgerPosting.TYPE_OFFICER_ADVANCE,
        amount=voucher.amount,
        debit_gl=emp_gl,
        credit_gl=gm_gl,
        reference_type="officer_payment_voucher",
        reference_id=voucher.voucher_no,
        memo=f"Officer advance to {voucher.officer_name} against {voucher.mpo.mpo_number}",
        user=user,
    )
    voucher.ledger_posting = posting
    voucher.save(update_fields=["ledger_posting"])
    return posting


def post_supplier_payment_voucher(payment_order, user):
    settings = ensure_fund_control_accounts()
    gm_gl = settings.gm_operating_gl
    task = payment_order.grn.lpo.project_task
    supplier = payment_order.grn.lpo.supplier
    if not supplier:
        raise ValueError("Supplier is required for GL supplier control posting.")
    sup_gl = ensure_supplier_control_gl(supplier)

    assert_task_can_disburse(task, payment_order.amount, require_ceo_gate=True)

    posting = _post_entry(
        task=task,
        posting_type=GLLedgerPosting.TYPE_SUPPLIER_PAYMENT,
        amount=payment_order.amount,
        debit_gl=sup_gl,
        credit_gl=gm_gl,
        reference_type="payment_order",
        reference_id=payment_order.pay_order_no,
        memo=f"Supplier payment {supplier.description} GRN {payment_order.grn.grn_no}",
        user=user,
    )
    payment_order.ledger_posting = posting
    payment_order.save(update_fields=["ledger_posting"])
    return posting

def post_task_disbursement_payment(payment, user):
    settings = ensure_fund_control_accounts()
    gm_gl = settings.gm_operating_gl
    expense_gl, _ = GLAccount.objects.get_or_create(
        gl_account_id="GL-GM-EXPENSE",
        defaults={
            "debit_credit": "DR",
            "description": "GM task expense clearing",
            "currency": "USD",
            "amount": Decimal("0.00"),
            "account_role": GLAccount.ROLE_GM_OPERATING,
        },
    )

    assert_task_can_disburse(payment.task, payment.amount, require_ceo_gate=True)

    return _post_entry(
        task=payment.task,
        posting_type=GLLedgerPosting.TYPE_GM_EXPENSE,
        amount=payment.amount,
        debit_gl=expense_gl,
        credit_gl=gm_gl,
        reference_type="task_disbursement_payment",
        reference_id=payment.payment_number,
        memo=f"GM disbursement - {payment.description}"[:200],
        user=user,
    )
