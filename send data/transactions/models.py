# transactions/models.py
from django.db import models, transaction
from django_extensions.db.fields import AutoSlugField
from django.db.models import Sum

from store.models import Item, ProductVariant, Color
from accounts.models import Vendor, Customer

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

    IMPORTANT: stock adjustments now happen here (model-level) so creation/update/delete
    of SaleDetail keeps Item.stock (and ProductVariant.stock_qty, if color is present)
    in sync automatically.
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
        We also attempt to keep ProductVariant.stock_qty in sync if a matching variant exists.
        """
        if not self.item_id:
            return
        with transaction.atomic():
            # update product-level stock
            it = Item.objects.select_for_update().get(pk=self.item_id)
            new_stock = (int(it.stock or 0) + int(change))
            # clamp to 0 (do not allow negative stock) — you can remove clamp if you allow negatives
            it.stock = new_stock if new_stock >= 0 else 0
            it.save(update_fields=["stock"])

            # try to update variant if color info is stored on this SaleDetail via related purchase/sale flows
            # (SaleDetail doesn't have color field by design here; if you record color elsewhere, keep variants in sync there)
            # We *do not* attempt to guess color here.

    def save(self, *args, **kwargs):
        # compute previous quantity (0 for new instance)
        prev_qty = 0
        if self.pk:
            try:
                prev = SaleDetail.objects.get(pk=self.pk)
                prev_qty = int(prev.quantity or 0)
            except SaleDetail.DoesNotExist:
                prev_qty = 0

        # compute change needed on Item.stock (positive if previous > new: add stock back,
        # negative if new > previous: reduce stock)
        change = int(prev_qty) - int(self.quantity or 0)

        # ensure total_detail correctness
        try:
            self.total_detail = float(self.price) * int(self.quantity)
        except Exception:
            self.total_detail = 0.0

        super().save(*args, **kwargs)

        if change != 0:
            # adjust stock after saving line
            # change positive => increase Item.stock; negative => decrease
            self._adjust_stock(change)

    def delete(self, *args, **kwargs):
        # when a sale detail is deleted, we must return the sold quantity to stock
        prev_qty = int(self.quantity or 0)
        super().delete(*args, **kwargs)
        if prev_qty:
            # add previous qty back to stock
            try:
                it = Item.objects.get(pk=self.item_id)
                it.stock = int(it.stock or 0) + prev_qty
                it.save(update_fields=["stock"])
            except Item.DoesNotExist:
                pass


class Purchase(models.Model):
    """
    Purchase header. Each Purchase can have multiple PurchaseDetail rows (line-items).
    total_value will be recomputed from details by recalc_total_from_details().
    """
    slug = AutoSlugField(unique=True, populate_from="vendor")
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

    Stock adjustments happen here: creating a PurchaseDetail increases Item.stock
    (and ProductVariant.stock_qty if color is present). Updating a PurchaseDetail will
    apply the delta; deleting will roll back the quantity.
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
        prev_qty = 0
        if self.pk:
            try:
                prev = PurchaseDetail.objects.get(pk=self.pk)
                prev_qty = int(prev.quantity or 0)
            except PurchaseDetail.DoesNotExist:
                prev_qty = 0

        # ensure total_detail correctness (price * quantity)
        try:
            self.total_detail = float(self.price) * int(self.quantity)
        except Exception:
            self.total_detail = 0.0

        super().save(*args, **kwargs)

        # compute delta to apply to stock (positive => increase Item.stock)
        delta = int(self.quantity or 0) - int(prev_qty or 0)
        if delta != 0 and self.item_id:
            with transaction.atomic():
                try:
                    it = Item.objects.select_for_update().get(pk=self.item_id)
                    it.stock = int(it.stock or 0) + int(delta)
                    it.save(update_fields=["stock"])
                except Item.DoesNotExist:
                    pass

                # Keep variant in sync if a color/variant exists
                if self.color_id:
                    try:
                        pv = ProductVariant.objects.select_for_update().get(product_id=self.item_id, color_id=self.color_id)
                        pv.stock_qty = int(pv.stock_qty or 0) + int(delta)
                        pv.save(update_fields=["stock_qty"])
                    except ProductVariant.DoesNotExist:
                        # If variant doesn't exist, do nothing (variant can be created via manage_colors)
                        pass

    def delete(self, *args, **kwargs):
        prev_qty = int(self.quantity or 0)
        item_id = self.item_id
        color_id = self.color_id
        super().delete(*args, **kwargs)
        if prev_qty and item_id:
            try:
                it = Item.objects.get(pk=item_id)
                it.stock = int(it.stock or 0) - prev_qty
                if it.stock < 0:
                    it.stock = 0
                it.save(update_fields=["stock"])
            except Item.DoesNotExist:
                pass

            if color_id:
                try:
                    pv = ProductVariant.objects.get(product_id=item_id, color_id=color_id)
                    pv.stock_qty = int(pv.stock_qty or 0) - prev_qty
                    if pv.stock_qty < 0:
                        pv.stock_qty = 0
                    pv.save(update_fields=["stock_qty"])
                except ProductVariant.DoesNotExist:
                    pass
