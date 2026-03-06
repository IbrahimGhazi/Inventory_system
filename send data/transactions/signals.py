# transactions/signals.py
import logging
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver

from transactions.models import PurchaseDetail
from store.models import Item, ProductVariant

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=PurchaseDetail)
def _store_previous_purchase_detail_qty(sender, instance: PurchaseDetail, **kwargs):
    """
    Store previous quantity on the instance (if it exists) so post_save can compute delta.
    This avoids guessing how much changed on update.
    """
    try:
        if instance.pk:
            try:
                prev = sender.objects.get(pk=instance.pk)
                instance._previous_quantity = int(prev.quantity or 0)
            except sender.DoesNotExist:
                instance._previous_quantity = 0
        else:
            instance._previous_quantity = 0
    except Exception:
        # Never let signals raise — just log and continue
        logger.exception("Failed to fetch previous PurchaseDetail quantity")


@receiver(post_save, sender=PurchaseDetail)
def purchase_detail_created_or_updated(sender, instance: PurchaseDetail, created, **kwargs):
    """
    Update stock when a PurchaseDetail is created or updated.
    - On create: add instance.quantity to the related Item or ProductVariant.
    - On update: compute delta (new - old) and apply that delta to stock.
    """
    try:
        prev_qty = getattr(instance, "_previous_quantity", 0)
        new_qty = int(instance.quantity or 0)
        delta = new_qty - int(prev_qty or 0)

        if delta == 0:
            return  # nothing to do

        # If the line refers to a color/variant, update ProductVariant.stock_qty
        if instance.color_id:
            # get_or_create variant (if it doesn't exist yet)
            variant, _ = ProductVariant.objects.get_or_create(
                product=instance.item,
                color=instance.color,
                defaults={"sku": f"SKU-{instance.item.pk}-{instance.color.pk}-AUTO", "stock_qty": 0}
            )
            old = int(variant.stock_qty or 0)
            variant.stock_qty = old + delta
            # ensure non-negative
            if variant.stock_qty < 0:
                variant.stock_qty = 0
            variant.save(update_fields=["stock_qty"])
            logger.debug("Adjusted variant pk=%s stock: %s -> %s (delta=%s)", variant.pk, old, variant.stock_qty, delta)
        else:
            # update Item.quantity
            item = instance.item
            if not item:
                logger.warning("PurchaseDetail %s has no item while updating stock", instance.pk)
                return
            old = int(item.quantity or 0)
            item.quantity = old + delta
            if item.quantity < 0:
                item.quantity = 0
            item.save(update_fields=["quantity"])
            logger.debug("Adjusted item pk=%s quantity: %s -> %s (delta=%s)", item.pk, old, item.quantity, delta)

    except Exception:
        logger.exception("Error in purchase_detail_created_or_updated")


@receiver(post_delete, sender=PurchaseDetail)
def purchase_detail_deleted(sender, instance: PurchaseDetail, **kwargs):
    """
    Roll back stock when a PurchaseDetail is deleted.
    Subtract the deleted line's quantity from Item or ProductVariant.
    """
    try:
        qty = int(instance.quantity or 0)
        if qty == 0:
            return

        if instance.color_id:
            try:
                variant = ProductVariant.objects.get(product=instance.item, color=instance.color)
                old = int(variant.stock_qty or 0)
                variant.stock_qty = max(0, old - qty)
                variant.save(update_fields=["stock_qty"])
                logger.debug("Decremented variant pk=%s stock: %s -> %s (removed=%s)", variant.pk, old, variant.stock_qty, qty)
            except ProductVariant.DoesNotExist:
                logger.warning("Variant not found while deleting PurchaseDetail %s", instance.pk)
        else:
            item = instance.item
            if not item:
                logger.warning("PurchaseDetail %s has no item while deleting", instance.pk)
                return
            old = int(item.quantity or 0)
            item.quantity = max(0, old - qty)
            item.save(update_fields=["quantity"])
            logger.debug("Decremented item pk=%s quantity: %s -> %s (removed=%s)", item.pk, old, item.quantity, qty)

    except Exception:
        logger.exception("Error in purchase_detail_deleted")
