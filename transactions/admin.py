# transactions/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse

from .models import Sale, SaleDetail, Purchase, PurchaseDetail


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "date_added", "grand_total", "amount_paid", "amount_change")
    list_filter = ("date_added", "customer")
    search_fields = ("customer__phone", "customer__first_name", "customer__last_name")
    ordering = ("-date_added",)
    readonly_fields = ("date_added",)
    date_hierarchy = "date_added"


@admin.register(SaleDetail)
class SaleDetailAdmin(admin.ModelAdmin):
    list_display = ("id", "sale", "item", "quantity", "price", "total_detail")
    list_select_related = ("sale", "item")
    search_fields = ("item__name", "sale__id")
    list_filter = ("sale",)


class PurchaseDetailInline(admin.TabularInline):
    model = PurchaseDetail
    extra = 1
    fields = ("item", "color", "quantity", "price", "total_detail")
    readonly_fields = ("total_detail",)
    autocomplete_fields = ("item", "color")


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ("id", "vendor", "order_date", "delivery_date", "total_quantity", "total_value", "delivery_status")
    list_select_related = ("vendor",)
    ordering = ("-order_date",)
    search_fields = ("vendor__name", "vendor__phone", "slug")
    readonly_fields = ("total_value",)
    inlines = (PurchaseDetailInline,)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related("purchase_details", "vendor")

    def total_quantity(self, obj):
        return sum((det.quantity or 0) for det in obj.purchase_details.all())
    total_quantity.short_description = "Total Qty"


@admin.register(PurchaseDetail)
class PurchaseDetailAdmin(admin.ModelAdmin):
    list_display = ("id", "purchase_link", "item", "color", "quantity", "price", "total_detail")
    list_select_related = ("purchase", "item", "color")
    search_fields = ("item__name", "purchase__vendor__name", "purchase__slug")

    def purchase_link(self, obj):
        if not obj.purchase_id:
            return "-"
        url = reverse("admin:transactions_purchase_change", args=(obj.purchase_id,))
        return format_html('<a href="{}">#{}</a>', url, obj.purchase_id)
    purchase_link.short_description = "Purchase"
