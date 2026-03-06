# transactions/signals.py
"""
IMPORTANT
========================================
Stock logic for PurchaseDetail is handled
ONLY in transactions/models.py:

- PurchaseDetail.save()
- PurchaseDetail.delete()

All PurchaseDetail stock signals are
DISABLED to prevent double stock updates.

DO NOT re-enable these unless you first
remove stock logic from models.py.
========================================
"""

import logging
# from django.db.models.signals import pre_save, post_save, post_delete
# from django.dispatch import receiver

# from transactions.models import PurchaseDetail
# from store.models import Item, ProductVariant

logger = logging.getLogger(__name__)


# @receiver(pre_save, sender=PurchaseDetail)
# def _store_previous_purchase_detail_qty(sender, instance: PurchaseDetail, **kwargs):
#     """
#     Store previous quantity on the instance (if it exists) so post_save can compute delta.
#     This avoids guessing how much changed on update.
#     """
#     try:
#         if instance.pk:
#             try:
#                 prev = sender.objects.get(pk=instance.pk)
#                 instance._previous_quantity = int(prev.quantity or 0)
#             except sender.DoesNotExist:
#                 instance._previous_quantity = 0
#         else:
#             instance._previous_quantity = 0
#     except Exception:
#         # Never let signals raise — just log and continue
#         logger.exception("Failed to fetch previous PurchaseDetail quantity")


# @receiver(post_save, sender=PurchaseDetail)
# def purchase_detail_created_or_updated(sender, instance: PurchaseDetail, created, **kwargs):
#     """
#     Update stock when a PurchaseDetail is created or updated.
#     - On create: add instance.quantity to the related Item or ProductVariant.
#     - On update: compute delta (new - old) and apply that delta to stock.
#     """
#     try:
#         prev_qty = getattr(instance, "_previous_quantity", 0)
#         new_qty = int(instance.quantity or 0)
#         delta = new_qty - int(prev_qty or 0)
#
#         if delta == 0:
#             return  # nothing to do
#
#         if instance.color_id:
#             variant, _ = ProductVariant.objects.get_or_create(
#                 product=instance.item,
#                 color=instance.color,
#                 defaults={
#                     "sku": f"SKU-{instance.item.pk}-{instance.color.pk}-AUTO",
#                     "stock_qty": 0
#                 }
#             )
#             variant.stock_qty = max(0, int(variant.stock_qty or 0) + delta)
#             variant.save(update_fields=["stock_qty"])
#         else:
#             item = instance.item
#             if not item:
#                 return
#             item.quantity = max(0, int(item.quantity or 0) + delta)
#             item.save(update_fields=["quantity"])
#
#     except Exception:
#         logger.exception("Error in purchase_detail_created_or_updated")


# @receiver(post_delete, sender=PurchaseDetail)
# def purchase_detail_deleted(sender, instance: PurchaseDetail, **kwargs):
#     """
#     Roll back stock when a PurchaseDetail is deleted.
#     """
#     try:
#         qty = int(instance.quantity or 0)
#         if qty == 0:
#             return
#
#         if instance.color_id:
#             try:
#                 variant = ProductVariant.objects.get(
#                     product=instance.item,
#                     color=instance.color
#                 )
#                 variant.stock_qty = max(0, int(variant.stock_qty or 0) - qty)
#                 variant.save(update_fields=["stock_qty"])
#             except ProductVariant.DoesNotExist:
#                 pass
#         else:
#             item = instance.item
#             if not item:
#                 return
#             item.quantity = max(0, int(item.quantity or 0) - qty)
#             item.save(update_fields=["quantity"])
#
#     except Exception:
#         logger.exception("Error in purchase_detail_deleted")
