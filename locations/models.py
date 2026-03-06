from django.db import models, transaction
from django.conf import settings
from django_extensions.db.fields import AutoSlugField


COMPANY_CHOICES = [
    ('NF', 'Naughtyfish'),
    ('SS', 'SeaStar'),
]


class Region(models.Model):
    name      = models.CharField(max_length=100, unique=True)
    slug      = AutoSlugField(unique=True, populate_from='name')
    company   = models.CharField(max_length=2, choices=COMPANY_CHOICES)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f'{self.get_company_display()} – {self.name}'

    class Meta:
        ordering = ['company', 'name']


class Store(models.Model):
    region    = models.ForeignKey(Region, on_delete=models.PROTECT, related_name='stores')
    name      = models.CharField(max_length=100)
    slug      = AutoSlugField(unique=True, populate_from='name')
    address   = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f'{self.name} ({self.region.name})'

    @property
    def company(self):
        return self.region.company

    class Meta:
        unique_together = ('region', 'name')
        ordering = ['region__name', 'name']


class StoreStock(models.Model):
    store    = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='stock_entries')
    item     = models.ForeignKey('store.Item', on_delete=models.CASCADE, related_name='store_stocks')
    quantity = models.IntegerField(default=0)

    class Meta:
        unique_together = ('store', 'item')
        ordering = ['store', 'item__name']

    def __str__(self):
        return f'{self.store.name} | {self.item.name} | qty={self.quantity}'

    @classmethod
    def adjust(cls, store, item, delta):
        """Thread-safe stock adjustment. delta is + or -."""
        with transaction.atomic():
            obj, _ = cls.objects.select_for_update().get_or_create(
                store=store, item=item,
                defaults={'quantity': 0}
            )
            obj.quantity = max(0, obj.quantity + int(delta))
            obj.save(update_fields=['quantity'])
        return obj

    @classmethod
    def global_total(cls, item):
        """Sum of this item's quantity across ALL stores."""
        from django.db.models import Sum
        result = cls.objects.filter(item=item).aggregate(t=Sum('quantity'))
        return result['t'] or 0


class StockTransfer(models.Model):
    from_store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name='transfers_out')
    to_store   = models.ForeignKey(Store, on_delete=models.PROTECT, related_name='transfers_in')
    item       = models.ForeignKey('store.Item', on_delete=models.PROTECT, related_name='transfers')
    quantity   = models.PositiveIntegerField()
    note       = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            StoreStock.adjust(self.from_store, self.item, -self.quantity)
            StoreStock.adjust(self.to_store,   self.item, +self.quantity)
            # sync global cache on Item
            from store.models import Item
            Item.objects.filter(pk=self.item_id).update(
                stock=StoreStock.global_total(self.item)
            )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Transfer {self.quantity}x {self.item.name}: {self.from_store} → {self.to_store}'