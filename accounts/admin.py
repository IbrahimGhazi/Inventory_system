# accounts/admin.py
from django.contrib import admin
from .models import Profile, Vendor, Customer, Payment


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "telephone", "email", "role", "status")


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("name", "phone_number", "address")
    search_fields = ("name", "phone_number", "address")


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("id", "first_name", "last_name", "phone", "balance")
    search_fields = ("first_name", "last_name", "phone")
    readonly_fields = ("total_invoiced", "total_paid", "balance")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "amount", "date", "cheque_number", "created_by")
    list_filter = ("date",)
    search_fields = ("customer__first_name", "customer__last_name", "cheque_number")
