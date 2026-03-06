# InventoryMS/urls.py
from django.conf import settings
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),

    # prefer redirecting root to store app
    path('', RedirectView.as_view(url='/store/', permanent=False)),

    # main app includes
    path('store/', include('store.urls')),
    path('staff/', include('accounts.urls')),
    path('transactions/', include('transactions.urls')),
    path('accounts/', include('accounts.urls')),
    path('invoice/', include('invoice.urls')),
    path('bills/', include('bills.urls')),
]

# serve static and media files in DEBUG mode (local dev convenience)
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    if getattr(settings, "MEDIA_URL", None):
        urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
