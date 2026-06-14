# accounts/forms.py
from django import forms
from .models import ProjectBudget, LPOTransaction

class BudgetForm(forms.ModelForm):
    class Meta:
        model = ProjectBudget
        fields = ['material_total_cost', 'labour_burden', 'misc_reserve', 'total_authorized_budget']

class LPOTransactionForm(forms.ModelForm):
    class Meta:
        model = LPOTransaction
        fields = ['supplier_contact', 'total_amount']