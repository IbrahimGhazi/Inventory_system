# invoice/forms.py

from decimal import Decimal, InvalidOperation

from django import forms
from django.forms import inlineformset_factory
from django.core.exceptions import ValidationError

from .models import Invoice, InvoiceItem
from accounts.models import Customer
from store.models import Item


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ["customer", "shipping"]
        labels = {
            "customer": "Customer",
            "shipping": "Shipping & Handling",
        }
        widgets = {
            "customer": forms.Select(attrs={"class": "form-control"}),
            "shipping": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Customer.objects.order_by(
            "first_name", "last_name"
        )


class InvoiceItemForm(forms.ModelForm):
    class Meta:
        model = InvoiceItem
        fields = (
            "item",
            "quantity",
            "price_per_item",
            "discount",
            "custom_name",
        )
        widgets = {
            "item": forms.Select(attrs={"class": "form-control item-select"}),
            "quantity": forms.NumberInput(
                attrs={"class": "form-control qty-input", "step": "0.01"}
            ),
            "price_per_item": forms.NumberInput(
                attrs={"class": "form-control price-input", "step": "0.01"}
            ),
            "discount": forms.NumberInput(
                attrs={"class": "form-control discount-input", "step": "0.01"}
            ),
            "custom_name": forms.TextInput(
                attrs={
                    "class": "form-control custom-name-input",
                    "placeholder": "Custom product name (if any)",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["item"].required = False
        self.fields["custom_name"].required = False
        self.fields["item"].queryset = Item.objects.order_by("name")

    def clean(self):
        cleaned = super().clean()
        item = cleaned.get("item")
        qty = cleaned.get("quantity")

        if not item:
            return cleaned

        try:
            qty_dec = Decimal(qty or 0)
        except (InvalidOperation, TypeError):
            raise ValidationError("Quantity must be a number.")

        if qty_dec < 0:
            raise ValidationError("Quantity cannot be negative.")

        old_qty = Decimal("0.00")
        if self.instance and self.instance.pk:
            try:
                old = InvoiceItem.objects.get(pk=self.instance.pk)
                old_qty = Decimal(old.quantity or 0)
            except InvoiceItem.DoesNotExist:
                pass

        delta = qty_dec - old_qty

        if delta > 0:
            available = item.stock or 0
            if int(delta) > available:
                raise ValidationError(
                    f"Not enough stock for {item.name}. "
                    f"Available: {available}, required: {int(delta)}."
                )

        return cleaned


InvoiceItemFormSet = inlineformset_factory(
    Invoice,
    InvoiceItem,
    form=InvoiceItemForm,
    extra=1,
    can_delete=True,
)
