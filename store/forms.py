# UTF-8
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Sum

from .models import Item, Category, Delivery, ProductVariant, Color


class ItemForm(forms.ModelForm):
    """Create/update an Item (base product). Price and product-level stock live here."""
    class Meta:
        model = Item
        fields = ['name', 'description', 'category', 'price', 'vendor', 'stock']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Item name'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Short description'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'vendor': forms.Select(attrs={'class': 'form-control'}),
            'stock': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '1'}),
        }
        labels = {
            'name': 'Item name',
            'price': 'Unit price (Rs)',
            'stock': 'Total stock (units)',
        }

    def clean_stock(self):
        v = self.cleaned_data.get('stock')
        if v is None:
            return 0
        try:
            iv = int(v)
        except (TypeError, ValueError):
            raise ValidationError("Stock must be an integer.")
        if iv < 0:
            raise ValidationError("Stock cannot be negative.")
        return iv


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter category name',
                'aria-label': 'Category Name'
            }),
        }
        labels = {'name': 'Category Name'}


class DeliveryForm(forms.ModelForm):
    class Meta:
        model = Delivery
        fields = ['item', 'customer_name', 'phone_number', 'location', 'date', 'is_delivered']
        widgets = {
            'item': forms.Select(attrs={'class': 'form-control', 'placeholder': 'Select item'}),
            'customer_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter customer name'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter phone number'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter delivery location'}),
            'date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'is_delivered': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ProductVariantForm(forms.ModelForm):
    # kept for admin / migration usage
    class Meta:
        model = ProductVariant
        fields = ['product', 'color', 'sku', 'stock_qty']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-control'}),
            'color': forms.Select(attrs={'class': 'form-control color-select'}),
            'sku': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'SKU (optional)'}),
            'stock_qty': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '1'}),
        }
        labels = {
            'stock_qty': 'Stock quantity',
            'sku': 'SKU',
        }

    def clean_stock_qty(self):
        v = self.cleaned_data.get('stock_qty')
        if v is None:
            return 0
        try:
            iv = int(v)
        except (TypeError, ValueError):
            raise ValidationError("Stock must be an integer.")
        if iv < 0:
            raise ValidationError("Stock cannot be negative.")
        return iv


class ColorForm(forms.ModelForm):
    class Meta:
        model = Color
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Color name (e.g. Piano black)',
                'autofocus': True
            }),
        }
        labels = {'name': 'Color name'}

    def clean_name(self):
        name = self.cleaned_data.get('name') or ''
        name = ' '.join(name.split())
        if not name:
            raise ValidationError("Color name cannot be empty.")
        qs = Color.objects.filter(name__iexact=name)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("A color with this name already exists.")
        return name


# Filters for /products (inventory-only: remove color filter)
class ItemFilterForm(forms.Form):
    q = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'class': 'form-control', 'placeholder': 'Search name...'
    }))
    category = forms.ModelChoiceField(
        queryset=Category.objects.all(), required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    in_stock = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={
        'class': 'form-check-input'
    }))
