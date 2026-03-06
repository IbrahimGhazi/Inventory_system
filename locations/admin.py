from django.contrib import admin
from .models import Region, Store, StoreStock, StockTransfer


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ['name', 'company', 'is_active']
    list_filter  = ['company', 'is_active']


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ['name', 'region', 'is_active']
    list_filter  = ['region__company', 'region', 'is_active']


@admin.register(StoreStock)
class StoreStockAdmin(admin.ModelAdmin):
    list_display  = ['store', 'item', 'quantity']
    list_filter   = ['store__region__company', 'store']
    search_fields = ['item__name']


@admin.register(StockTransfer)
class StockTransferAdmin(admin.ModelAdmin):
    list_display = ['item', 'quantity', 'from_store', 'to_store', 'created_at', 'created_by']
    list_filter  = ['from_store', 'to_store']