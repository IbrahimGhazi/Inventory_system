from django import forms
from .models import Region, Store, StockTransfer, StoreStock


class RegionForm(forms.ModelForm):
    class Meta:
        model = Region
        fields = ['name', 'company', 'is_active']
        widgets = {
            'name':      forms.TextInput(attrs={'class': 'form-control'}),
            'company':   forms.Select(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class StoreForm(forms.ModelForm):
    class Meta:
        model = Store
        fields = ['region', 'name', 'address', 'is_active']
        widgets = {
            'region':    forms.Select(attrs={'class': 'form-control'}),
            'name':      forms.TextInput(attrs={'class': 'form-control'}),
            'address':   forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class StockTransferForm(forms.ModelForm):
    class Meta:
        model = StockTransfer
        fields = ['from_store', 'to_store', 'item', 'quantity', 'note']
        widgets = {
            'from_store': forms.Select(attrs={'class': 'form-control'}),
            'to_store':   forms.Select(attrs={'class': 'form-control'}),
            'item':       forms.Select(attrs={'class': 'form-control'}),
            'quantity':   forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'note':       forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def clean(self):
        cleaned = super().clean()
        from_store = cleaned.get('from_store')
        to_store   = cleaned.get('to_store')
        item       = cleaned.get('item')
        quantity   = cleaned.get('quantity')

        if from_store and to_store and from_store == to_store:
            raise forms.ValidationError("Source and destination store cannot be the same.")

        if from_store and item and quantity:
            try:
                ss = StoreStock.objects.get(store=from_store, item=item)
                if ss.quantity < quantity:
                    raise forms.ValidationError(
                        f"Not enough stock. {from_store.name} only has {ss.quantity} units of {item.name}."
                    )
            except StoreStock.DoesNotExist:
                raise forms.ValidationError(
                    f"{from_store.name} has no stock of {item.name}."
                )
        return cleaned