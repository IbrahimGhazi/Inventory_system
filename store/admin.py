from django.contrib import admin
from .models import Category, Color, Item, ProductVariant, Delivery


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name',)
    ordering = ('name',)


# show ProductVariant inline is removed so admin item pages show product-level stock only
@admin.display(description="Total Stock")
def total_stock(obj: Item):
    return obj.total_stock()


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'stock', total_stock, 'price', 'vendor')
    search_fields = ('name', 'category__name', 'vendor__name')
    list_filter = ('category', 'vendor')
    ordering = ('name',)
    # inlines removed in Phase-1 to hide color-based editing from the main item page
    # if you still want to access variants you can go to ProductVariantAdmin below


@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name', 'slug')
    ordering = ('name',)


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    # keep this registration so variants remain editable for migration / admin purposes,
    # but they are not shown inline on the Item admin (reduces accidental edits).
    list_display = ('product', 'color', 'sku', 'stock_qty')
    search_fields = ('sku', 'product__name', 'color__name')
    list_filter = ('product', 'color')
    ordering = ('product__name', 'color__name')


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ('item', 'customer_name', 'phone_number', 'location', 'date', 'is_delivered')
    search_fields = ('item__name', 'customer_name')
    list_filter = ('is_delivered', 'date')
    ordering = ('-date',)
