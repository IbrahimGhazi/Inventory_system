# Django core imports
from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

# Local app imports
from .views import (
    InvoiceListView,
    InvoiceDetailView,
    InvoiceCreateView,
    InvoiceUpdateView,
    InvoiceDeleteView,
)

urlpatterns = [
    # List all invoices
    path(
        'invoices/',
        InvoiceListView.as_view(),
        name='invoicelist'
    ),

    # Create new invoice
    path(
        'new-invoice/',
        InvoiceCreateView.as_view(),
        name='invoice-create'
    ),

    # View invoice detail (standard HTML or fallback)
    path(
        'invoice/<slug:slug>/',
        InvoiceDetailView.as_view(),
        name='invoice-detail'
    ),

    # View invoice in PDF-style layout (new route)
    path(
        'invoice/<int:pk>/pdf/',
        InvoiceDetailView.as_view(),
        name='invoice-pdf'
    ),

    # API endpoints used by the invoice JS
    path('api/item/<int:pk>/colors/', views.api_item_colors, name='api_item_colors'),
    path('api/item/<int:pk>/price/', views.api_item_price, name='api_item_price'),

    # Update existing invoice
    path(
        'invoice/<slug:slug>/update/',
        InvoiceUpdateView.as_view(),
        name='invoice-update'
    ),

    # Delete invoice
    path(
        'invoice/<int:pk>/delete/',
        InvoiceDeleteView.as_view(),
        name='invoice-delete'
    ),
]

# Static media for development
if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )
