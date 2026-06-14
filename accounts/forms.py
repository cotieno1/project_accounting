from django import forms
from django.forms import inlineformset_factory
from .models import ProjectBudget, LPOTransaction, LPOItem

class BudgetForm(forms.ModelForm):
    class Meta:
        model = ProjectBudget
        fields = ['material_total_cost', 'labour_burden', 'misc_reserve', 'total_authorized_budget']

class LPOTransactionForm(forms.ModelForm):
    class Meta:
        model = LPOTransaction
        fields = ['supplier_contact', 'total_amount']

# This allows you to manage multiple LPOItems for one LPOTransaction
LPOItemFormSet = inlineformset_factory(
    LPOTransaction, 
    LPOItem, 
    fields=('description', 'uom', 'qty', 'unit_price', 'total_price', 'rfq_no'),
    extra=1,      # Number of empty forms to show
    can_delete=True
)