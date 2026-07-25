from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.forms import inlineformset_factory
from .models import ProjectBudget, LPOTransaction, LPOItem


class MobileFriendlyLoginForm(AuthenticationForm):
    """
    Phone keyboards often capitalize the first letter or autocorrect usernames,
    and users sometimes paste a trailing space or type their email instead.
    Resolve those before authenticate() so mobile login matches desktop.
    """

    username = forms.CharField(
        label="Username or email",
        widget=forms.TextInput(
            attrs={
                "autocapitalize": "none",
                "autocorrect": "off",
                "spellcheck": "false",
                "autocomplete": "username",
                "inputmode": "text",
                "class": "form-control",
            }
        ),
    )

    def clean_username(self):
        raw = (self.cleaned_data.get("username") or "").strip()
        if not raw:
            return raw
        User = get_user_model()
        user = User.objects.filter(username__iexact=raw).first()
        if user is None and "@" in raw:
            user = User.objects.filter(email__iexact=raw).first()
        if user is None and "@" in raw:
            # Staff emails often live on UserAccount, not auth.User.email
            from .models import UserAccount
            ua = (
                UserAccount.objects.select_related("user")
                .filter(email__iexact=raw, user__isnull=False)
                .first()
            )
            if ua is not None:
                user = ua.user
        return user.username if user is not None else raw



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