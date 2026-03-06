# accounts/models.py
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.urls import reverse
from django.apps import apps

from django_extensions.db.fields import AutoSlugField
from imagekit.models import ProcessedImageField
from imagekit.processors import ResizeToFill
from phonenumber_field.modelfields import PhoneNumberField


# Profile / Vendor (kept from your original file, cleaned)
STATUS_CHOICES = [
    ("INA", "Inactive"),
    ("A", "Active"),
    ("OL", "On leave"),
]

ROLE_CHOICES = [
    ("OP", "Operative"),
    ("EX", "Executive"),
    ("AD", "Admin"),
]


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    slug = AutoSlugField(unique=True, populate_from="email", verbose_name="Account ID")
    profile_picture = ProcessedImageField(
        default="profile_pics/default.jpg",
        upload_to="profile_pics",
        format="JPEG",
        processors=[ResizeToFill(150, 150)],
        options={"quality": 100},
    )
    telephone = PhoneNumberField(null=True, blank=True)
    email = models.EmailField(max_length=150, blank=True, null=True)
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=30, blank=True)
    status = models.CharField(choices=STATUS_CHOICES, max_length=12, default="INA")
    role = models.CharField(choices=ROLE_CHOICES, max_length=12, blank=True, null=True)
    default_store = models.ForeignKey(
        'locations.Store',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='staff_profiles'
    )

    def __str__(self):
        return f"{self.user.username} Profile"

    @property
    def image_url(self):
        try:
            return self.profile_picture.url
        except Exception:
            return ""

    class Meta:
        ordering = ["slug"]
        verbose_name = "Profile"
        verbose_name_plural = "Profiles"


class Vendor(models.Model):
    name = models.CharField(max_length=50)
    slug = AutoSlugField(unique=True, populate_from="name")
    phone_number = models.BigIntegerField(blank=True, null=True)
    address = models.CharField(max_length=50, blank=True, null=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Vendor"
        verbose_name_plural = "Vendors"


# ----------------------------
# Customer + Payment (balance)
# ----------------------------
class Customer(models.Model):
    """
    Customer model with cached financial totals:
      - total_invoiced : Decimal (sum of related invoice grand_total)
      - total_paid     : Decimal (sum of related payments)
      - balance        : Decimal (invoiced - paid)
    Methods:
      - get_full_name()
      - to_select2()
      - update_balance()
    """
    first_name = models.CharField(max_length=256)
    last_name = models.CharField(max_length=256, blank=True, null=True)
    address = models.TextField(max_length=256, blank=True, null=True)
    phone = models.CharField(max_length=30, blank=True, null=True)
    
    last_updated_at = models.DateTimeField(auto_now=True)

    total_invoiced = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        db_table = "Customers"
        verbose_name = "Customer"
        verbose_name_plural = "Customers"

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name or ''}".strip()

    def get_full_name(self):
        return f"{self.first_name} {self.last_name or ''}".strip()

    def to_select2(self):
        return {"label": self.get_full_name(), "value": self.id}

    def update_balance(self):
        """
        Recalculate totals based on related models:
          - invoices (related_name='invoices' expected on Invoice model)
          - payments (related_name='payments' used below)
        If invoice model is missing, invoiced_total remains 0.
        """
        # Sum invoices (if invoice app/model exists)
        invoiced_total = Decimal("0.00")
        try:
            Invoice = apps.get_model("invoice", "Invoice")
            invoiced_agg = Invoice.objects.filter(customer=self).aggregate(total=models.Sum("grand_total"))
            invoiced_total = invoiced_agg.get("total") or Decimal("0.00")
        except LookupError:
            invoiced_total = Decimal("0.00")

        # Sum payments
        payments_agg = self.payments.aggregate(total=models.Sum("amount"))
        paid_total = payments_agg.get("total") or Decimal("0.00")

        # Normalize to Decimal
        try:
            invoiced_total = Decimal(invoiced_total)
        except Exception:
            invoiced_total = Decimal(str(invoiced_total or "0"))

        try:
            paid_total = Decimal(paid_total)
        except Exception:
            paid_total = Decimal(str(paid_total or "0"))

        self.total_invoiced = invoiced_total
        self.total_paid = paid_total
        # balance = invoiced - paid (positive means customer owes money)
        self.balance = (invoiced_total - paid_total).quantize(Decimal("0.01"))
        self.save(update_fields=["total_invoiced", "total_paid", "balance"])


class Payment(models.Model):
    """
    Payment recorded from a customer. Saving/deleting updates the linked customer's cached totals.
    """
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="payments")
    date = models.DateField(default=timezone.now)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    last_updated_at = models.DateTimeField(auto_now=True)
    
    cheque_number = models.CharField(max_length=100, blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        db_table = "Payments"
        ordering = ["-date"]
        verbose_name = "Payment"
        verbose_name_plural = "Payments"

    def __str__(self):
        return f"Payment {self.amount} from {self.customer.get_full_name()}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # update customer's cached totals
        try:
            self.customer.update_balance()
        except Exception:
            pass

    def delete(self, *args, **kwargs):
        cust = self.customer
        super().delete(*args, **kwargs)
        try:
            cust.update_balance()
        except Exception:
            pass
