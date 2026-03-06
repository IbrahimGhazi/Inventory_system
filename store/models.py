# -*- coding: utf-8 -*-
"""
Models: Category, Color, Item (now with stock), ProductVariant (kept for backwards compatibility),
Delivery.

Phase-1 change: Item now has a canonical `stock` field (product-level stock).
ProductVariant and Color kept for migration / history; total_stock() prefers item.stock
but falls back to variant sums when stock is zero (helps pre-migration visibility).
"""
from django.db import models
from django.urls import reverse
from django.forms import model_to_dict
from django_extensions.db.fields import AutoSlugField
from phonenumber_field.modelfields import PhoneNumberField
from django.db.models import Sum

from accounts.models import Vendor


class Category(models.Model):
    name = models.CharField(max_length=50)
    slug = AutoSlugField(unique=True, populate_from='name')

    def __str__(self):
        return f"Category: {self.name}"

    class Meta:
        verbose_name_plural = 'Categories'


class Color(models.Model):
    name = models.CharField(max_length=30, unique=True)
    slug = AutoSlugField(unique=True, populate_from='name')

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class Item(models.Model):
    """
    Base product. Price is invariant across colors.
    New: `stock` is the product-level stock quantity used by inventory pages.
    ProductVariant remains for per-color records until you remove it later.
    """
    slug = AutoSlugField(unique=True, populate_from='name')
    name = models.CharField(max_length=50)
    description = models.TextField(max_length=256, blank=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)

    # New canonical product-level stock (inventory view uses this field)
    stock = models.PositiveIntegerField(default=0)

    # Legacy field kept for compatibility (you can remove later)
    quantity = models.IntegerField(default=0)

    price = models.FloatField(default=0)
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.name} - Category: {self.category} - Stock: {self.total_stock()}"

    def get_absolute_url(self):
        return reverse('item-detail', kwargs={'slug': self.slug})

    def total_stock(self) -> int:
        """
        Return authoritative stock value for display:
          - if item.stock (product-level) is non-zero, return it
          - otherwise fall back to sum of variant.stock_qty (helps pre-migration)
        This provides a safe, visible transition for Phase-1.
        """
        # Prefer product-level stock after migration
        if self.stock and self.stock > 0:
            return int(self.stock)

        # Fallback: sum variants (old behavior)
        agg = self.variants.aggregate(total=Sum('stock_qty')) if hasattr(self, 'variants') else {}
        return int(agg.get('total') or 0)

    def get_price(self) -> float:
        return float(self.price or 0)

    def to_json(self):
        product = model_to_dict(self, fields=['name', 'description', 'price'])
        product['id'] = self.id
        product['text'] = self.name
        product['category'] = self.category.name if self.category else ""
        product['quantity'] = 1
        product['total_product'] = 0
        product['total_stock'] = self.total_stock()
        return product

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Items'


class ProductVariant(models.Model):
    """
    Per-color stock. Kept for migration/historical data while we move to product-level stock.
    """
    product = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='variants')
    color = models.ForeignKey(Color, on_delete=models.PROTECT, related_name='variants')
    sku = models.CharField(max_length=64, unique=True, blank=True)
    stock_qty = models.IntegerField(default=0)

    class Meta:
        unique_together = ('product', 'color')
        ordering = ['product__name', 'color__name']

    def __str__(self):
        return f"{self.product.name} - {self.color.name}"

    def get_price(self) -> float:
        return self.product.get_price()


class Delivery(models.Model):
    item = models.ForeignKey(Item, blank=True, null=True, on_delete=models.SET_NULL)
    customer_name = models.CharField(max_length=30, blank=True, null=True)
    phone_number = PhoneNumberField(blank=True, null=True)
    location = models.CharField(max_length=20, blank=True, null=True)
    date = models.DateTimeField()
    is_delivered = models.BooleanField(default=False, verbose_name='Is Delivered')

    def __str__(self):
        return f"Delivery of {self.item} to {self.customer_name} at {self.location} on {self.date}"
