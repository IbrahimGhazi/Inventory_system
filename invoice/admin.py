from django.contrib import admin
from .models import Invoice, InvoiceItem


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1
    fields = ('item', 'quantity', 'price_per_item')
    # You can make fields read-only if you wish:
    # readonly_fields = ('total',)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    inlines = [InvoiceItemInline]

    # What you see in the change form
    fields = (
        'customer',
        'shipping',
        'total',
        'grand_total',
        'date',
    )
    readonly_fields = ('total', 'grand_total', 'date')

    # What you see in the list
    list_display = (
        'id',
        'date',
        'customer',
        'shipping',
        'total',
        'grand_total',
    )
    list_select_related = ('customer',)
    list_filter = ('date',)
    search_fields = (
        'customer__first_name',
        'customer__last_name',
        'customer__phone',
    )


@admin.register(InvoiceItem)
class InvoiceItemAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'item', 'quantity', 'price_per_item', 'total_display')
    list_select_related = ('invoice', 'item')

    def total_display(self, obj):
        return obj.total
    total_display.short_description = 'Total'
