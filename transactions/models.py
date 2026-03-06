from django.db import models, transaction
from django.db.models import Sum
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from store.models import Item, ProductVariant, Color
from accounts.models import Vendor, Customer

import uuid

DELIVERY_CHOICES = [("P", "Pending"), ("S", "Successful")]


class Sale(models.Model):
    date_added = models.DateTimeField(auto_now_add=True, verbose_name="Sale Date")
    customer = models.ForeignKey(Customer, on_delete=models.DO_NOTHING, db_column="customer")
    sub_total = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    grand_total = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    tax_percentage = models.FloatField(default=0.0)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    amount_change = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)

    class Meta:
        db_table = "sales"
        verbose_name = "Sale"
        verbose_name_plural = "Sales"

    def __str__(self):
        return f"Sale ID: {self.id} | Grand Total: {self.grand_total} | Date: {self.date_added}"

    def sum_products(self):
        return sum(detail.quantity for detail in self.saledetail_set.all())


class SaleDetail(models.Model):
    """
    Line item for a sale.

    Stock adjustments happen at model-level using delta logic so updates/deletes keep Item.stock
    (and ProductVariant.stock_qty, if color is present) in sync.
    """
    sale = models.ForeignKey(
        Sale, on_delete=models.CASCADE, db_column="sale", related_name="saledetail_set"
    )
    item = models.ForeignKey(
        Item, on_delete=models.SET_NULL, null=True, blank=True, db_column="item", related_name="sale_details"
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()
    total_detail = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = "sale_details"
        verbose_name = "Sale Detail"
        verbose_name_plural = "Sale Details"

    def __str__(self):
        return f"Detail ID: {self.id} | Sale ID: {self.sale.id} | Quantity: {self.quantity}"

    def _adjust_stock(self, change):
        """
        change: positive => increase stock on Item (undoing a sale)
                negative => reduce stock on Item (applying a sale)
        Uses select_for_update to avoid races.
        """
        if not self.item_id:
            return
        with transaction.atomic():
            try:
                it = Item.objects.select_for_update().get(pk=self.item_id)
                new_stock = (int(it.stock or 0) + int(change))
                it.stock = new_stock if new_stock >= 0 else 0
                it.save(update_fields=["stock"])
            except Item.DoesNotExist:
                return

            # If you manage ProductVariant stock elsewhere, keep it in sync there.
            # SaleDetail does not store color in this design.

    def save(self, *args, **kwargs):
        # compute previous quantity (0 for new instance)
        prev_qty = 0
        if self.pk:
            try:
                prev = SaleDetail.objects.get(pk=self.pk)
                prev_qty = int(prev.quantity or 0)
            except SaleDetail.DoesNotExist:
                prev_qty = 0

        # ensure total_detail correctness
        try:
            self.total_detail = float(self.price) * int(self.quantity)
        except Exception:
            self.total_detail = 0.0

        super().save(*args, **kwargs)

        # change: prev_qty - new_qty (positive => add back stock, negative => reduce)
        change = int(prev_qty) - int(self.quantity or 0)
        if change != 0:
            self._adjust_stock(change)

    def delete(self, *args, **kwargs):
        # when a sale detail is deleted, return the sold quantity to stock
        prev_qty = int(self.quantity or 0)
        # delete the model row first, then adjust stocks in a transaction
        super().delete(*args, **kwargs)
        if prev_qty:
            try:
                with transaction.atomic():
                    it = Item.objects.select_for_update().get(pk=self.item_id)
                    it.stock = int(it.stock or 0) + prev_qty
                    it.save(update_fields=["stock"])
            except Item.DoesNotExist:
                pass


class Purchase(models.Model):
    """
    Purchase header. Each Purchase can have multiple PurchaseDetail rows (line-items).
    total_value will be recomputed from details by recalc_total_from_details().
    """
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    store = models.ForeignKey(                              # ← ADD
        'locations.Store',                                  # ← ADD
        on_delete=models.PROTECT,                           # ← ADD
        null=True, blank=True,                              # ← null=True for migration safety
        related_name='purchases'                            # ← ADD
    )
    vendor = models.ForeignKey(Vendor, related_name="purchases", on_delete=models.CASCADE)
    description = models.TextField(max_length=300, blank=True, null=True)
    order_date = models.DateTimeField(auto_now_add=True)
    delivery_date = models.DateTimeField(blank=True, null=True, verbose_name="Delivery Date")
    delivery_status = models.CharField(choices=DELIVERY_CHOICES, max_length=1, default="S")
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)  # legacy: kept for compatibility
    total_value = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)

    class Meta:
        ordering = ["order_date"]

    def save(self, *args, **kwargs):
        if not self.delivery_status:
            self.delivery_status = "S"
        super().save(*args, **kwargs)

    def recalc_total_from_details(self):
        total = 0.0
        for det in self.purchase_details.all():
            try:
                total += float(det.total_detail or 0.0)
            except Exception:
                pass
        self.total_value = total
        self.save(update_fields=["total_value"])

    def __str__(self):
        return f"{self.vendor.name} - {self.order_date}"


class PurchaseDetail(models.Model):
    """
    One line in a Purchase.

    Stock adjustments happen here. Important change: save() will apply stock **only on CREATE**.
    Updates are expected to be handled via delete() + create() pattern (views do this).
    """
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="purchase_details")
    item = models.ForeignKey(Item, on_delete=models.SET_NULL, null=True, blank=True, related_name="purchase_details")
    color = models.ForeignKey(Color, on_delete=models.SET_NULL, null=True, blank=True, related_name="purchase_detail_colors")
    quantity = models.PositiveIntegerField(default=0)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    total_detail = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)

    class Meta:
        db_table = "purchase_details"
        verbose_name = "Purchase Detail"
        verbose_name_plural = "Purchase Details"

    def save(self, *args, **kwargs):
        """
        Apply stock only when this is a new PurchaseDetail (is_new True).
        This avoids double-counting when the update flow deletes old rows and creates new ones.
        """
        is_new = self.pk is None

        # ensure total_detail correctness (price * quantity)
        try:
            self.total_detail = float(self.price) * int(self.quantity)
        except Exception:
            self.total_detail = 0.0

        super().save(*args, **kwargs)

        if is_new and self.item_id and int(self.quantity or 0) != 0:
            store = getattr(self.purchase, 'store', None)
            if store:
                from locations.models import StoreStock
                StoreStock.adjust(store, self.item, +int(self.quantity))
                # sync global Item.stock cache
                Item.objects.filter(pk=self.item_id).update(
                    stock=StoreStock.global_total(self.item)
                )
            else:
                # fallback: no store assigned yet (legacy rows)
                with transaction.atomic():
                    try:
                        it = Item.objects.select_for_update().get(pk=self.item_id)
                        it.stock = int(it.stock or 0) + int(self.quantity or 0)
                        it.save(update_fields=["stock"])
                    except Item.DoesNotExist:
                        pass

                # keep variant in sync if a color/variant exists
                if self.color_id:
                    try:
                        pv = ProductVariant.objects.select_for_update().get(product_id=self.item_id, color_id=self.color_id)
                        pv.stock_qty = int(pv.stock_qty or 0) + int(self.quantity or 0)
                        pv.save(update_fields=["stock_qty"])
                    except ProductVariant.DoesNotExist:
                        pass

    def delete(self, *args, **kwargs):
        prev_qty = int(self.quantity or 0)
        item_id = self.item_id
        color_id = self.color_id
        # delete the model row first, then adjust stock safely under a transaction using select_for_update
        super().delete(*args, **kwargs)
        if prev_qty and item_id:
            store = getattr(getattr(self, 'purchase', None), 'store', None)
            if store:
                from locations.models import StoreStock
                from store.models import Item
                StoreStock.adjust(store, self.item, -prev_qty)
                Item.objects.filter(pk=item_id).update(
                    stock=StoreStock.global_total(self.item)
                )
            else:
                with transaction.atomic():
                    try:
                        it = Item.objects.select_for_update().get(pk=item_id)
                        it.stock = max(0, int(it.stock or 0) - prev_qty)
                        it.save(update_fields=["stock"])
                    except Item.DoesNotExist:
                        pass

                if color_id:
                    try:
                        pv = ProductVariant.objects.select_for_update().get(product_id=item_id, color_id=color_id)
                        pv.stock_qty = int(pv.stock_qty or 0) - prev_qty
                        if pv.stock_qty < 0:
                            pv.stock_qty = 0
                        pv.save(update_fields=["stock_qty"])
                    except ProductVariant.DoesNotExist:
                        pass


@receiver(pre_delete, sender=Purchase)
def _purchase_pre_delete(sender, instance: Purchase, **kwargs):
    """
    Ensure that when a Purchase is deleted (including via QuerySet.delete or cascade)
    each PurchaseDetail.delete() is invoked so stock rollback logic runs.
    We iterate over a list() to evaluate before any DB-level cascade removes rows.
    """
    # delete details individually so that PurchaseDetail.delete() runs and adjusts stocks
    for det in list(instance.purchase_details.all()):
        try:
            det.delete()
        except Exception:
            # swallow exceptions here to avoid preventing purchase deletion;
            # you can log/raise depending on your needs
            pass
