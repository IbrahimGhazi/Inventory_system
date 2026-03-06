from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import logging
import uuid

from django.db import models, transaction
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django_extensions.db.fields import AutoSlugField

from store.models import Item
from accounts.models import Customer

logger = logging.getLogger(__name__)


def _to_decimal(value):
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


# ===========================
# Invoice
# ===========================

class Invoice(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False,unique=True, null=True)
    date = models.DateTimeField(auto_now_add=True, verbose_name="Date (e.g., 2022/11/22)")
    last_updated_at = models.DateTimeField(auto_now=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="invoices")
    store = models.ForeignKey(          # ← ADD
        'locations.Store',              # ← ADD
        on_delete=models.PROTECT,       # ← ADD
        null=True, blank=True,          # ← null=True for migration safety
        related_name='invoices'         # ← ADD
    )

    shipping = models.DecimalField(
        verbose_name="Shipping and Handling",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    total = models.DecimalField(
        verbose_name="Total Amount (Rs)",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        editable=False,
    )

    grand_total = models.DecimalField(
        verbose_name="Grand Total (Rs)",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        editable=False,
    )

    class Meta:
        ordering = ["-date"]
        indexes = [models.Index(fields=["date"])]

    def _recalculate_totals(self):
        total = Decimal("0.00")
        for it in self.items.all():
            total += _to_decimal(it.total)

        self.total = total.quantize(Decimal("0.01"))
        self.grand_total = (self.total + _to_decimal(self.shipping)).quantize(Decimal("0.01"))

    def save(self, *args, **kwargs):
        creating = self.pk is None

        if creating:
            super().save(*args, **kwargs)

        self._recalculate_totals()

        if creating:
            super().save(update_fields=["total", "grand_total"])
        else:
            super().save(*args, **kwargs)

        try:
            if self.customer_id:
                self.customer.update_balance()
        except Exception:
            logger.exception("Failed to update customer balance for invoice %s", self.pk)


# ===========================
# Invoice Item (NO COLOR)
# ===========================

class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")

    item = models.ForeignKey(
        Item,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoice_items",
    )

    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    price_per_item = models.DecimalField(
        verbose_name="Price Per Item (Rs)",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    discount = models.DecimalField(
        verbose_name="Discount (%)",
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    custom_name = models.CharField(max_length=200, null=True, blank=True)

    @property
    def total(self):
        q = _to_decimal(self.quantity)
        p = _to_decimal(self.price_per_item)
        subtotal = q * p

        disc = _to_decimal(self.discount) or Decimal("0.00")
        if disc:
            factor = (Decimal("100.00") - disc) / Decimal("100.00")
            return (subtotal * factor).quantize(Decimal("0.01"))

        return subtotal.quantize(Decimal("0.01"))

    def __str__(self):
        name = getattr(self.item, "name", None) or self.custom_name or "Deleted / Custom Item"
        return f"{name} x {self.quantity}"


# ===========================
# Helpers
# ===========================

def _update_invoice_and_customer(invoice: Invoice):
    if not invoice.pk:
        return

    invoice._recalculate_totals()
    Invoice.objects.filter(pk=invoice.pk).update(
        total=invoice.total,
        grand_total=invoice.grand_total,
    )

    try:
        if invoice.customer_id:
            customer = Customer.objects.filter(pk=invoice.customer_id).first()
            if customer:
                customer.update_balance()
    except Exception:
        logger.exception(
            "Failed to update customer balance after invoice change: %s", invoice.pk
        )


# ===========================
# Signals — totals
# ===========================

@receiver(post_save, sender=InvoiceItem)
def on_item_saved_update_totals(sender, instance, **kwargs):
    try:
        _update_invoice_and_customer(instance.invoice)
    except Exception:
        logger.exception(
            "Failed to update invoice totals in post_save for InvoiceItem %s",
            getattr(instance, "pk", None),
        )


@receiver(post_delete, sender=InvoiceItem)
def on_item_deleted_update_totals(sender, instance, **kwargs):
    try:
        _update_invoice_and_customer(instance.invoice)
    except Exception:
        logger.exception(
            "Failed to update invoice totals in post_delete for InvoiceItem %s",
            getattr(instance, "pk", None),
        )


# ===========================
# Signals — stock (ITEM BASED)
# ===========================

@receiver(pre_save, sender=InvoiceItem)
def invoiceitem_pre_save(sender, instance, **kwargs):
    if not instance.pk:
        instance._old_quantity = Decimal("0.00")
        instance._old_item_id = None
        return

    try:
        old = InvoiceItem.objects.get(pk=instance.pk)
        instance._old_quantity = _to_decimal(old.quantity)
        instance._old_item_id = old.item_id
    except InvoiceItem.DoesNotExist:
        instance._old_quantity = Decimal("0.00")
        instance._old_item_id = None
    except Exception:
        instance._old_quantity = Decimal("0.00")
        instance._old_item_id = None
        logger.exception(
            "Error fetching previous InvoiceItem state for %s",
            getattr(instance, "pk", None),
        )


@receiver(post_save, sender=InvoiceItem)
def invoiceitem_post_save_adjust_stock(sender, instance, created, **kwargs):
    try:
        if not instance.item:
            return

        new_qty = _to_decimal(instance.quantity)
        old_qty = getattr(instance, "_old_quantity", Decimal("0.00"))
        delta = new_qty - old_qty

        try:
            int_delta = int(delta.quantize(0, rounding=ROUND_HALF_UP))
        except Exception:
            int_delta = int(delta)

        if int_delta == 0:
            return

        store = getattr(instance.invoice, 'store', None)

        with transaction.atomic():
            if store:
                from locations.models import StoreStock
                # int_delta > 0 means more items invoiced → reduce store stock
                StoreStock.adjust(store, instance.item, -int_delta)
                instance.item.stock = StoreStock.global_total(instance.item)
                instance.item.save(update_fields=["stock"])
            else:
                # no store assigned → fall back to global Item.stock
                if int_delta > 0:
                    instance.item.stock = max(0, instance.item.stock - int_delta)
                else:
                    instance.item.stock = instance.item.stock - int_delta
                instance.item.save(update_fields=["stock"])

    except Exception:
        logger.exception(
            "Failed to adjust stock in invoiceitem_post_save_adjust_stock for InvoiceItem %s",
            getattr(instance, "pk", None),
        )


@receiver(post_delete, sender=InvoiceItem)
def invoiceitem_post_delete_restore_stock(sender, instance, **kwargs):
    try:
        if not instance.item:
            return

        try:
            qty = int(_to_decimal(instance.quantity).quantize(0, rounding=ROUND_HALF_UP))
        except Exception:
            qty = int(_to_decimal(instance.quantity))

        store = getattr(instance.invoice, 'store', None)

        with transaction.atomic():
            if store:
                from locations.models import StoreStock
                StoreStock.adjust(store, instance.item, +qty)
                instance.item.stock = StoreStock.global_total(instance.item)
                instance.item.save(update_fields=["stock"])
            else:
                instance.item.stock += qty
                instance.item.save(update_fields=["stock"])

    except Exception:
        logger.exception(
            "Failed to restore stock on InvoiceItem deletion for %s",
            getattr(instance, "pk", None),
        )
