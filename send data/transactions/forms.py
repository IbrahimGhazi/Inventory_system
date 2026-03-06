# transactions/forms.py
from django import forms
from django.forms import inlineformset_factory
from .models import Sale, Purchase, PurchaseDetail, SaleDetail
from store.models import Item, Color


class BootstrapMixin(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            if existing:
                field.widget.attrs["class"] = existing + " form-control"
            else:
                field.widget.attrs.setdefault("class", "form-control")


class SaleForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Sale
        fields = ["customer", "tax_percentage", "amount_paid"]
        widgets = {
            "tax_percentage": forms.NumberInput(attrs={"step": "0.01"}),
            "amount_paid": forms.NumberInput(attrs={"step": "0.01"}),
        }


class PurchaseForm(BootstrapMixin, forms.ModelForm):
    total_value = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "readonly": "readonly"})
    )

    class Meta:
        model = Purchase
        fields = ["vendor", "description", "delivery_date", "total_value"]
        widgets = {
            "delivery_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "description": forms.Textarea(attrs={"rows": 2}),
        }


class PurchaseDetailForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = PurchaseDetail
        fields = ["item", "color", "quantity", "price", "total_detail"]
        widgets = {
            "item": forms.Select(attrs={"class": "form-control"}),
            "color": forms.Select(attrs={"class": "form-control"}),
            "quantity": forms.NumberInput(attrs={"min": 0}),
            "price": forms.NumberInput(attrs={"step": "0.01"}),
            "total_detail": forms.NumberInput(attrs={"step": "0.01", "readonly": "readonly"}),
        }

    def clean(self):
        cleaned = super().clean()
        try:
            qty = int(cleaned.get("quantity") or 0)
            price = float(cleaned.get("price") or 0.0)
            cleaned["total_detail"] = price * qty
        except Exception:
            cleaned["total_detail"] = 0.0
        return cleaned


PurchaseDetailFormSet = inlineformset_factory(
    Purchase,
    PurchaseDetail,
    form=PurchaseDetailForm,
    extra=1,
    can_delete=True,
    min_num=0,
)
