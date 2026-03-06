"""
signals.py – Django signals for ALL models.
Every save/delete fires the corresponding sync function.
All exceptions are swallowed so the app never crashes due to sync issues.
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from accounts.models import Profile, Vendor, Customer, Payment
from store.models import Category, Color, Item, ProductVariant
from transactions.models import Sale, SaleDetail, Purchase, PurchaseDetail
from invoice.models import Invoice, InvoiceItem
from bills.models import Bill
from locations.models import Region, Store, StoreStock, StockTransfer

from .supabase_sync import (
    sync_user, delete_user,
    sync_profile, delete_profile,
    sync_vendor, delete_vendor,
    sync_customer, delete_customer,
    sync_payment, delete_payment,
    sync_category, delete_category,
    sync_color, delete_color,
    sync_item, delete_item,
    sync_variant, delete_variant,
    sync_sale, delete_sale,
    sync_saledetail, delete_saledetail,
    sync_purchase, delete_purchase,
    sync_purchasedetail, delete_purchasedetail,
    sync_invoice, delete_invoice,
    sync_invoiceitem, delete_invoiceitem,
    sync_bill, delete_bill,
    sync_region, delete_region,
    sync_store, delete_store,
    sync_storestock, delete_storestock,
    sync_stocktransfer, delete_stocktransfer,
)

User = get_user_model()


def _safe(fn, *args):
    try:
        fn(*args)
    except Exception:
        pass


# ── auth.User ─────────────────────────────────────────────────────────────────
@receiver(post_save, sender=User)
def on_user_save(sender, instance, **kwargs):
    _safe(sync_user, instance)

@receiver(post_delete, sender=User)
def on_user_delete(sender, instance, **kwargs):
    _safe(delete_user, instance.pk)


# ── accounts ─────────────────────────────────────────────────────────────────
@receiver(post_save, sender=Profile)
def on_profile_save(sender, instance, **kwargs):
    _safe(sync_profile, instance)

@receiver(post_delete, sender=Profile)
def on_profile_delete(sender, instance, **kwargs):
    _safe(delete_profile, instance.pk)


@receiver(post_save, sender=Vendor)
def on_vendor_save(sender, instance, **kwargs):
    _safe(sync_vendor, instance)

@receiver(post_delete, sender=Vendor)
def on_vendor_delete(sender, instance, **kwargs):
    _safe(delete_vendor, instance.pk)


@receiver(post_save, sender=Customer)
def on_customer_save(sender, instance, **kwargs):
    _safe(sync_customer, instance)

@receiver(post_delete, sender=Customer)
def on_customer_delete(sender, instance, **kwargs):
    _safe(delete_customer, instance.pk)


@receiver(post_save, sender=Payment)
def on_payment_save(sender, instance, **kwargs):
    _safe(sync_payment, instance)
    _safe(sync_customer, instance.customer)

@receiver(post_delete, sender=Payment)
def on_payment_delete(sender, instance, **kwargs):
    _safe(delete_payment, instance.pk)
    _safe(sync_customer, instance.customer)


# ── store ─────────────────────────────────────────────────────────────────────
@receiver(post_save, sender=Category)
def on_category_save(sender, instance, **kwargs):
    _safe(sync_category, instance)

@receiver(post_delete, sender=Category)
def on_category_delete(sender, instance, **kwargs):
    _safe(delete_category, instance.pk)


@receiver(post_save, sender=Color)
def on_color_save(sender, instance, **kwargs):
    _safe(sync_color, instance)

@receiver(post_delete, sender=Color)
def on_color_delete(sender, instance, **kwargs):
    _safe(delete_color, instance.pk)


@receiver(post_save, sender=Item)
def on_item_save(sender, instance, **kwargs):
    _safe(sync_item, instance)

@receiver(post_delete, sender=Item)
def on_item_delete(sender, instance, **kwargs):
    _safe(delete_item, instance.pk)


@receiver(post_save, sender=ProductVariant)
def on_variant_save(sender, instance, **kwargs):
    _safe(sync_variant, instance)

@receiver(post_delete, sender=ProductVariant)
def on_variant_delete(sender, instance, **kwargs):
    _safe(delete_variant, instance.pk)


# ── transactions ──────────────────────────────────────────────────────────────
@receiver(post_save, sender=Sale)
def on_sale_save(sender, instance, **kwargs):
    _safe(sync_sale, instance)

@receiver(post_delete, sender=Sale)
def on_sale_delete(sender, instance, **kwargs):
    _safe(delete_sale, instance.pk)


@receiver(post_save, sender=SaleDetail)
def on_saledetail_save(sender, instance, **kwargs):
    _safe(sync_saledetail, instance)

@receiver(post_delete, sender=SaleDetail)
def on_saledetail_delete(sender, instance, **kwargs):
    _safe(delete_saledetail, instance.pk)


@receiver(post_save, sender=Purchase)
def on_purchase_save(sender, instance, **kwargs):
    _safe(sync_purchase, instance)

@receiver(post_delete, sender=Purchase)
def on_purchase_delete(sender, instance, **kwargs):
    _safe(delete_purchase, instance.pk)


@receiver(post_save, sender=PurchaseDetail)
def on_purchasedetail_save(sender, instance, **kwargs):
    _safe(sync_purchasedetail, instance)

@receiver(post_delete, sender=PurchaseDetail)
def on_purchasedetail_delete(sender, instance, **kwargs):
    _safe(delete_purchasedetail, instance.pk)


# ── invoice ───────────────────────────────────────────────────────────────────
@receiver(post_save, sender=Invoice)
def on_invoice_save(sender, instance, **kwargs):
    _safe(sync_invoice, instance)
    _safe(sync_customer, instance.customer)

@receiver(post_delete, sender=Invoice)
def on_invoice_delete(sender, instance, **kwargs):
    _safe(delete_invoice, instance.pk)
    _safe(sync_customer, instance.customer)


@receiver(post_save, sender=InvoiceItem)
def on_invoiceitem_save(sender, instance, **kwargs):
    _safe(sync_invoiceitem, instance)

@receiver(post_delete, sender=InvoiceItem)
def on_invoiceitem_delete(sender, instance, **kwargs):
    _safe(delete_invoiceitem, instance.pk)


# ── bills ─────────────────────────────────────────────────────────────────────
@receiver(post_save, sender=Bill)
def on_bill_save(sender, instance, **kwargs):
    _safe(sync_bill, instance)

@receiver(post_delete, sender=Bill)
def on_bill_delete(sender, instance, **kwargs):
    _safe(delete_bill, instance.pk)


# ── locations ─────────────────────────────────────────────────────────────────
@receiver(post_save, sender=Region)
def on_region_save(sender, instance, **kwargs):
    _safe(sync_region, instance)

@receiver(post_delete, sender=Region)
def on_region_delete(sender, instance, **kwargs):
    _safe(delete_region, instance.pk)


@receiver(post_save, sender=Store)
def on_store_save(sender, instance, **kwargs):
    _safe(sync_store, instance)

@receiver(post_delete, sender=Store)
def on_store_delete(sender, instance, **kwargs):
    _safe(delete_store, instance.pk)


@receiver(post_save, sender=StoreStock)
def on_storestock_save(sender, instance, **kwargs):
    _safe(sync_storestock, instance)

@receiver(post_delete, sender=StoreStock)
def on_storestock_delete(sender, instance, **kwargs):
    _safe(delete_storestock, instance.pk)


@receiver(post_save, sender=StockTransfer)
def on_stocktransfer_save(sender, instance, **kwargs):
    _safe(sync_stocktransfer, instance)

@receiver(post_delete, sender=StockTransfer)
def on_stocktransfer_delete(sender, instance, **kwargs):
    _safe(delete_stocktransfer, instance.pk)
