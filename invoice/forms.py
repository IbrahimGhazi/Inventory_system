# invoice/forms.py
from decimal import Decimal, InvalidOperation

from django import forms
from django.forms import inlineformset_factory
from django.core.exceptions import ValidationError

from .models import Invoice, InvoiceItem
from accounts.models import Customer
from store.models import Item


class ItemChoiceField(forms.ModelChoiceField):
    """
    ModelChoiceField that embeds data-price and data-stock attributes into <option> tags.
    Tries several common attribute names so it works even if your model uses a different field name.
    """
    PRICE_ATTRS = ("price", "unit_price", "selling_price", "sell_price", "sale_price", "mrp", "cost")
    STOCK_ATTRS = ("stock", "quantity", "qty", "available_stock", "available", "instock")

    def label_from_instance(self, obj):
        # preserve default label behavior (uses __str__ / model representation)
        return super().label_from_instance(obj)

    def _find_attr(self, obj, names):
        for name in names:
            if hasattr(obj, name):
                val = getattr(obj, name)
                if val is None:
                    continue
                # Convert Decimal/number to string; safe fallback for other types
                try:
                    return str(val)
                except Exception:
                    return f"{val}"
        # return empty string when not found (JS will handle missing/empty)
        return ""

    def create_option(
        self, name, value, label, selected, index, subindex=None, attrs=None
    ):
        option = super().create_option(
            name, value, label, selected, index, subindex=subindex, attrs=attrs
        )

        # value may be a LazyObject-like; Django wraps instance under "value.instance"
        try:
            if value and hasattr(value, "instance"):
                item = value.instance
            else:
                # older Django may pass model instance directly as 'label' or 'value'
                item = None
        except Exception:
            item = None

        if item is not None:
            price = self._find_attr(item, self.PRICE_ATTRS)
            stock = self._find_attr(item, self.STOCK_ATTRS)

            # attach attributes (only set if not empty to keep HTML minimal)
            if price != "":
                option_attrs = option.setdefault("attrs", {})
                option_attrs["data-price"] = price
            if stock != "":
                option_attrs = option.setdefault("attrs", {})
                option_attrs["data-stock"] = stock

        return option


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ["store", "customer", "shipping"]
        labels = {
            "customer": "Customer",
            "shipping": "Shipping & Handling",
        }
        widgets = {
            "store": forms.Select(attrs={'class': 'form-control'}), 
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
    # Use the custom ItemChoiceField which adds data-price and data-stock
    item = ItemChoiceField(
        queryset=Item.objects.order_by("name"),
        required=False,
        widget=forms.Select(attrs={"class": "form-control item-select"}),
    )

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

        self.fields["custom_name"].required = False

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
            available = getattr(item, "stock", None) or 0
            if int(delta) > available:
                raise ValidationError(
                    f"Not enough stock for {item}. "
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
