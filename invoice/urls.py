# Django core imports
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

# Local app imports
from . import views
from .views import (
    InvoiceListView,
    InvoiceDetailView,
    InvoiceCreateView,
    InvoiceUpdateView,
    InvoiceDeleteView,
    api_items_for_store,
)

urlpatterns = [
    # ─────────────────────────────────────────────────────────────
    # List all invoices
    # ─────────────────────────────────────────────────────────────
    path(
        "invoices/",
        InvoiceListView.as_view(),
        name="invoicelist",
    ),

    # ─────────────────────────────────────────────────────────────
    # Create new invoice
    # ─────────────────────────────────────────────────────────────
    path(
        "new-invoice/",
        InvoiceCreateView.as_view(),
        name="invoice-create",
    ),

    # ─────────────────────────────────────────────────────────────
    # Invoice detail (HTML)
    # ─────────────────────────────────────────────────────────────
    path(
        "invoice/<uuid:uuid>/",
        InvoiceDetailView.as_view(),
        name="invoice-detail",
    ),

    # ─────────────────────────────────────────────────────────────
    # Invoice PDF view (USES UUID — FIXED)
    # ─────────────────────────────────────────────────────────────
    path(
        "invoice/<uuid:uuid>/pdf/",
        InvoiceDetailView.as_view(),
        name="invoice-pdf",
    ),

    # ─────────────────────────────────────────────────────────────
    # API endpoints used by invoice JS (remain PK-based, OK)
    # ─────────────────────────────────────────────────────────────
    path(
        "api/item/<int:pk>/colors/",
        views.api_item_colors,
        name="api_item_colors",
    ),
    path(
        "api/item/<int:pk>/price/",
        views.api_item_price,
        name="api_item_price",
    ),
    
    path(
        "api/items-for-store/",      # ← ADD THIS
        api_items_for_store,
        name="api_items_for_store",
    ),

    # ─────────────────────────────────────────────────────────────
    # Update invoice
    # ─────────────────────────────────────────────────────────────
    path(
        "invoice/<uuid:uuid>/update/",
        InvoiceUpdateView.as_view(),
        name="invoice-update",
    ),

    # ─────────────────────────────────────────────────────────────
    # Delete invoice (UUID — FIXED)
    # ─────────────────────────────────────────────────────────────
    path(
        "invoice/<uuid:uuid>/delete/",
        InvoiceDeleteView.as_view(),
        name="invoice-delete",
    ),
]

# ─────────────────────────────────────────────────────────────────
# Static media (development only)
# ─────────────────────────────────────────────────────────────────
if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )
