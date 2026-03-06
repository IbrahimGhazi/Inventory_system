# accounts/urls.py
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from django.contrib.auth import views as auth_views

from . import views

urlpatterns = [
    # Auth / profile
    path("register/", views.register, name="user-register"),
    path("login/", auth_views.LoginView.as_view(template_name="accounts/login.html"), name="user-login"),
    path("logout/", auth_views.LogoutView.as_view(template_name="accounts/logout.html"), name="user-logout"),
    path("profile/", views.profile, name="user-profile"),
    path("profile/update/", views.profile_update, name="user-profile-update"),

    # Staff - list and CRUD for Profile model (class-based views)
    path("profiles/", views.ProfileListView.as_view(), name="profile_list"),
    path("profiles/new/", views.ProfileCreateView.as_view(), name="profile-create"),
    path("profiles/<int:pk>/update/", views.ProfileUpdateView.as_view(), name="profile-update"),
    path("profiles/<int:pk>/delete/", views.ProfileDeleteView.as_view(), name="profile-delete"),

    # Create staff (User + Profile)
    path("staff/new/", views.create_staff, name="staff_create"),

    # Customers (canonical names)
    path("customers/", views.CustomerListView.as_view(), name="customer_list"),
    path("customers/create/", views.CustomerCreateView.as_view(), name="customer_create"),
    path("customers/<int:pk>/update/", views.CustomerUpdateView.as_view(), name="customer_update"),
    path("customers/<int:pk>/delete/", views.CustomerDeleteView.as_view(), name="customer_delete"),

    # Payments & ledger (canonical names)
    path("customers/<int:pk>/payment/", views.PaymentCreateView.as_view(), name="payment_create"),
    path("customers/<int:pk>/payments/", views.CustomerPaymentsList.as_view(), name="customer_payments_list"),
    path("customers/<int:pk>/ledger/", views.customer_ledger, name="customer_ledger"),
    path("payments/new/", views.PaymentCreateView.as_view(), name="payment-create"),

    # AJAX helpers
    path("get_customers/", views.get_customers, name="get_customers"),

    # Vendors
    path("vendors/", views.VendorListView.as_view(), name="vendor-list"),
    path("vendors/new/", views.VendorCreateView.as_view(), name="vendor-create"),
    path("vendors/<int:pk>/update/", views.VendorUpdateView.as_view(), name="vendor-update"),
    path("vendors/<int:pk>/delete/", views.VendorDeleteView.as_view(), name="vendor-delete"),
]

# --- Compatibility / legacy route names (aliases) ---
urlpatterns += [
    path("customers/", views.CustomerListView.as_view(), name="customerslist"),
    path("customers/<int:pk>/payments/", views.CustomerPaymentsList.as_view(), name="customer-payments-list"),
    path("customers/", views.CustomerListView.as_view(), name="customer-list"),
]

# Serve media in DEBUG
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
