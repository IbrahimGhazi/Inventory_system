# accounts/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Profile, Customer, Vendor, Payment


class CreateUserForm(UserCreationForm):
    """
    User creation form for staff. Includes first_name and last_name and saves them.
    """
    email = forms.EmailField(required=True)
    first_name = forms.CharField(required=False, max_length=30)
    last_name = forms.CharField(required=False, max_length=150)

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "password1", "password2"]

    def save(self, commit=True):
        # Populate standard user fields and save.
        user = super().save(commit=False)
        user.email = self.cleaned_data.get("email") or ""
        user.first_name = self.cleaned_data.get("first_name") or ""
        user.last_name = self.cleaned_data.get("last_name") or ""
        if commit:
            user.save()
        return user


class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["username", "email"]


class ProfileUpdateForm(forms.ModelForm):
    """
    Profile form used both for editing the current user's profile and for
    creating a Profile alongside a new User. Make profile fields optional
    here so staff creation won't be blocked if profile data is omitted.
    """
    class Meta:
        model = Profile
        fields = ["telephone", "email", "first_name", "last_name", "profile_picture"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Make all profile fields optional in this form so User creation is not blocked.
        for name, field in self.fields.items():
            field.required = False
            # add bootstrap class if not present
            css = field.widget.attrs.get("class", "")
            if "form-control" not in css and field.widget.__class__.__name__ != "ClearableFileInput":
                field.widget.attrs["class"] = (css + " form-control").strip()
            # file inputs typically are left alone; add helper class for them
            if field.widget.__class__.__name__ == "ClearableFileInput":
                field.widget.attrs.setdefault("class", "form-control-file")


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ["first_name", "last_name", "phone", "address"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Enter first name"}),
            "last_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Enter last name"}),
            "address": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Address"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "Phone"}),
        }


class VendorForm(forms.ModelForm):
    class Meta:
        model = Vendor
        fields = ["name", "phone_number", "address"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Vendor Name"}),
            "phone_number": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Phone Number"}),
            "address": forms.TextInput(attrs={"class": "form-control", "placeholder": "Address"}),
        }


class PaymentForm(forms.ModelForm):
    """
    If creating payment from a customer-specific page, the 'customer' field can be omitted.
    """
    class Meta:
        model = Payment
        fields = ["amount", "cheque_number", "remarks"]
        widgets = {
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "cheque_number": forms.TextInput(attrs={"class": "form-control"}),
            "remarks": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }
