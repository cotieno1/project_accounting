from django.contrib import admin
from .models import (
    UserAccount, UserCategory, Module, BankAccount, SupplierAccount,
    GLAnalysisCategory, GLAccount, ProjectTask, ProjectBuildCategory,
    Product, RequisitionOrder, RequisitionOrderItem, BOMHeader, BOMItem,
    ProjectBudget, BudgetTransaction, RFQTransaction, LPOTransaction,
    TaskDisbursementPayment,
)

# -------------------------------
# CORE ADMIN
# -------------------------------
@admin.register(UserAccount)
class UserAccountAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'first_name', 'last_name', 'designation', 'phone', 'email',
        'access_level', 'must_change_password', 'onboarding_email_sent_at',
        'onboarded_at',
    )
    search_fields = ('user__username', 'first_name', 'last_name', 'designation', 'email')
    list_filter = ('access_level', 'must_change_password')

@admin.register(UserCategory)
class UserCategoryAdmin(admin.ModelAdmin):
    list_display = ('code', 'description', 'rank')
    search_fields = ('code', 'description')
    ordering = ('-rank', 'description')
    filter_horizontal = ('modules',)

@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')

# -------------------------------
# BANK & SUPPLIER
# -------------------------------
@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ('bank_account_id', 'account_number', 'description', 'phone')
    search_fields = ('bank_account_id', 'description')

@admin.register(SupplierAccount)
class SupplierAccountAdmin(admin.ModelAdmin):
    list_display = ('supplier_id', 'description', 'phone', 'email')
    search_fields = ('supplier_id', 'description')

# -------------------------------
# GL & PROJECT
# -------------------------------
@admin.register(GLAnalysisCategory)
class GLAnalysisCategoryAdmin(admin.ModelAdmin):
    list_display = ('category_id', 'description')

@admin.register(GLAccount)
class GLAccountAdmin(admin.ModelAdmin):
    list_display = ('gl_account_id', 'description', 'debit_credit', 'currency', 'amount')
    list_filter = ('debit_credit', 'currency')
    search_fields = ('gl_account_id', 'description')

@admin.register(ProjectTask)
class ProjectTaskAdmin(admin.ModelAdmin):
    list_display = ('project_id', 'description')

@admin.register(ProjectBuildCategory)
class ProjectBuildCategoryAdmin(admin.ModelAdmin):
    list_display = ('build_cat_id', 'description')

# -------------------------------
# PROCUREMENT & BUDGET
# -------------------------------
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('product_id', 'description', 'unit_of_measure', 'stock_quantity')
    search_fields = ('product_id', 'description')


@admin.register(ProjectBudget)
class ProjectBudgetAdmin(admin.ModelAdmin):
    list_display = ('budget_label', 'budget_type', 'task', 'total_authorized_budget', 'created_at')

@admin.register(BudgetTransaction)
class BudgetTransactionAdmin(admin.ModelAdmin):
    list_display = ('budget', 'category', 'amount', 'timestamp')
    list_filter = ('category', 'timestamp')


@admin.register(TaskDisbursementPayment)
class TaskDisbursementPaymentAdmin(admin.ModelAdmin):
    list_display = ('payment_number', 'task', 'budget_line', 'amount', 'payee', 'created_at')
    list_filter = ('budget_line', 'payment_method', 'created_at')
    search_fields = ('payment_number', 'description', 'payee')
    
@admin.register(LPOTransaction)
class LPOTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'lpo_no',
        'supplier',
        'project_task',
        'building',
        'build_category',
        'total_amount',
        'date_issued',
    )

    list_filter = ('supplier', 'project_task', 'date_issued')
    search_fields = (
        'lpo_no',
        'supplier__description',
        'project_task__description'
    )