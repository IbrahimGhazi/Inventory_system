# -*- coding: utf-8 -*-
from decimal import Decimal
import datetime as _dt

from django.apps import apps
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpRequest
from django.urls import reverse_lazy, reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib import messages

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.db.models import Q, Sum
from django.db import transaction

from django.utils import timezone

from .models import Profile, Customer, Vendor, Payment
from .forms import (
    CreateUserForm,
    UserUpdateForm,
    ProfileUpdateForm,
    CustomerForm,
    VendorForm,
    PaymentForm,
)
from .tables import ProfileTable  # optional, remove if unused


# ---------------------------
# Registration & Profile
# ---------------------------
def register(request):
    if request.method == "POST":
        form = CreateUserForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("user-login")
    else:
        form = CreateUserForm()
    return render(request, "accounts/register.html", {"form": form})


@login_required
def profile(request):
    return render(request, "accounts/profile.html")


@login_required
def profile_update(request):
    if request.method == "POST":
        u_form = UserUpdateForm(request.POST, instance=request.user)
        p_form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user.profile)
        if u_form.is_valid() and p_form.is_valid():
            u_form.save()
            p_form.save()
            return redirect("user-profile")
    else:
        u_form = UserUpdateForm(instance=request.user)
        p_form = ProfileUpdateForm(instance=request.user.profile)
    return render(request, "accounts/profile_update.html", {"u_form": u_form, "p_form": p_form})


# ---------------------------
# Create Staff (User + Profile)
# ---------------------------
@login_required
def create_staff(request: HttpRequest):
    """
    Create a new User (via CreateUserForm) and linked Profile (via ProfileUpdateForm).
    This view is debug-friendly: on invalid POST it prints diagnostics to server console
    and renders debug information in the page (so you can see what failed).
    """
    if request.method == "POST":
        user_form = CreateUserForm(request.POST)
        profile_form = ProfileUpdateForm(request.POST, request.FILES)

        if user_form.is_valid() and profile_form.is_valid():
            with transaction.atomic():
                user = user_form.save()
                # Create profile and attach to user
                profile = profile_form.save(commit=False)
                profile.user = user
                profile.save()
            messages.success(request, "Staff account created successfully.")
            return redirect("profile_list")
        else:
            # Print debug to server console (check your runserver output)
            try:
                print("create_staff: user_form.is_valid() ->", user_form.is_valid())
                print("create_staff: user_form.errors ->", user_form.errors.as_json())
            except Exception:
                print("create_staff: could not serialize user_form.errors")

            try:
                print("create_staff: profile_form.is_valid() ->", profile_form.is_valid())
                print("create_staff: profile_form.errors ->", profile_form.errors.as_json())
            except Exception:
                print("create_staff: could not serialize profile_form.errors")

            debug_errors = {
                "user_errors": user_form.errors,
                "profile_errors": profile_form.errors,
                "posted": request.POST.dict(),
            }

            messages.error(request, "Please fix the errors shown below.")
            return render(request, "accounts/staff_create.html", {
                "user_form": user_form,
                "profile_form": profile_form,
                "debug_errors": debug_errors,
            })
    else:
        user_form = CreateUserForm()
        profile_form = ProfileUpdateForm()

    return render(request, "accounts/staff_create.html", {
        "user_form": user_form,
        "profile_form": profile_form,
    })


# ---------------------------
# Staff / Profile Views (CBV)
# ---------------------------
class ProfileListView(LoginRequiredMixin, ListView):
    model = Profile
    template_name = "accounts/stafflist.html"
    context_object_name = "profiles"
    paginate_by = 10


class ProfileCreateView(LoginRequiredMixin, CreateView):
    model = Profile
    template_name = "accounts/staffcreate.html"
    fields = ["user", "role", "status"]

    def get_success_url(self):
        return reverse_lazy("profile_list")

    def test_func(self):
        return self.request.user.is_superuser


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = Profile
    template_name = "accounts/staffupdate.html"
    fields = ["user", "role", "status"]

    def get_success_url(self):
        return reverse_lazy("profile_list")

    def test_func(self):
        return self.request.user.is_superuser


class ProfileDeleteView(LoginRequiredMixin, DeleteView):
    model = Profile
    template_name = "accounts/staffdelete.html"

    def get_success_url(self):
        return reverse_lazy("profile_list")

    def test_func(self):
        return self.request.user.is_superuser


# ---------------------------
# Customers (CRUD)
# ---------------------------
class CustomerListView(LoginRequiredMixin, ListView):
    model = Customer
    template_name = "accounts/customer_list.html"
    context_object_name = "customers"
    paginate_by = 25
    ordering = ["first_name"]

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(phone__icontains=q))
        return qs.order_by("first_name")


class CustomerCreateView(LoginRequiredMixin, CreateView):
    model = Customer
    template_name = "accounts/customer_form.html"
    form_class = CustomerForm
    success_url = reverse_lazy("customer_list")


class CustomerUpdateView(LoginRequiredMixin, UpdateView):
    model = Customer
    template_name = "accounts/customer_form.html"
    form_class = CustomerForm
    success_url = reverse_lazy("customer_list")


class CustomerDeleteView(LoginRequiredMixin, DeleteView):
    model = Customer
    template_name = "accounts/customer_confirm_delete.html"
    success_url = reverse_lazy("customer_list")


# ---------------------------
# Vendors
# ---------------------------
class VendorListView(LoginRequiredMixin, ListView):
    model = Vendor
    template_name = "accounts/vendor_list.html"
    context_object_name = "vendors"
    paginate_by = 10


class VendorCreateView(LoginRequiredMixin, CreateView):
    model = Vendor
    form_class = VendorForm
    template_name = "accounts/vendor_form.html"
    success_url = reverse_lazy("vendor-list")


class VendorUpdateView(LoginRequiredMixin, UpdateView):
    model = Vendor
    form_class = VendorForm
    template_name = "accounts/vendor_form.html"
    success_url = reverse_lazy("vendor-list")


class VendorDeleteView(LoginRequiredMixin, DeleteView):
    model = Vendor
    template_name = "accounts/vendor_confirm_delete.html"
    success_url = reverse_lazy("vendor-list")


# ---------------------------
# AJAX: search customers
# ---------------------------
def is_ajax(request):
    return request.META.get("HTTP_X_REQUESTED_WITH") == "XMLHttpRequest"


@login_required
@csrf_exempt
@require_POST
def get_customers(request):
    term = request.POST.get("term", "").strip()
    qs = Customer.objects.all()
    if term:
        qs = qs.filter(Q(first_name__icontains=term) | Q(last_name__icontains=term) | Q(phone__icontains=term))
    out = [{"id": c.id, "name": c.get_full_name()} for c in qs[:20]]
    return JsonResponse(out, safe=False)


# ---------------------------
# Payments & Ledger
# ---------------------------
class PaymentCreateView(LoginRequiredMixin, CreateView):
    model = Payment
    form_class = PaymentForm
    template_name = "accounts/payment_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.customer = get_object_or_404(Customer, pk=kwargs.get("pk"))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["customer"] = self.customer
        return ctx

    def form_valid(self, form):
        form.instance.customer = self.customer
        resp = super().form_valid(form)
        try:
            self.customer.update_balance()
        except Exception:
            pass
        messages.success(self.request, f"Recorded payment of {self.object.amount} for {self.customer.get_full_name()}.")
        return resp

    def get_success_url(self):
        return reverse("customer-payments-list", kwargs={"pk": self.customer.pk})


class CustomerPaymentsList(LoginRequiredMixin, ListView):
    model = Payment
    template_name = "accounts/customer_payments.html"
    context_object_name = "payments"
    paginate_by = 50

    def get_queryset(self):
        self.customer = get_object_or_404(Customer, pk=self.kwargs.get("pk"))
        return Payment.objects.filter(customer=self.customer).order_by("-date", "-pk")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["customer"] = self.customer
        ctx["balance"] = self.customer.balance
        ctx["total_invoiced"] = self.customer.total_invoiced
        ctx["total_paid"] = self.customer.total_paid
        ctx["object_list"] = ctx.get("payments", [])
        return ctx


@login_required
def customer_ledger(request, pk: int):
    customer = get_object_or_404(Customer, pk=pk)
    tz = timezone.get_current_timezone()

    def _to_aware_datetime(val):
        if val is None:
            return None
        if isinstance(val, _dt.datetime):
            if timezone.is_aware(val):
                try:
                    return val.astimezone(tz)
                except Exception:
                    return timezone.make_aware(val.replace(tzinfo=None), tz)
            else:
                try:
                    return timezone.make_aware(val, tz)
                except Exception:
                    return val.replace(tzinfo=tz)
        if isinstance(val, _dt.date):
            dt = _dt.datetime.combine(val, _dt.time.min)
            try:
                return timezone.make_aware(dt, tz)
            except Exception:
                return dt.replace(tzinfo=tz)
        if isinstance(val, str):
            try:
                parsed = _dt.datetime.fromisoformat(val)
                return _to_aware_datetime(parsed)
            except Exception:
                return None
        return None

    def _get_date_norm(obj):
        for attr in ("date", "order_date", "date_added", "created_at", "timestamp"):
            val = getattr(obj, attr, None)
            if val is not None:
                d = _to_aware_datetime(val)
                if d is not None:
                    return d
        try:
            pk_val = int(getattr(obj, "pk", 0) or 0)
        except Exception:
            pk_val = 0
        fallback = _dt.datetime(1970, 1, 1) + _dt.timedelta(seconds=pk_val)
        return timezone.make_aware(fallback, tz)

    invoices = []
    try:
        Invoice = apps.get_model("invoice", "Invoice")
        if Invoice is not None:
            invoices = list(Invoice.objects.filter(customer=customer))
    except Exception:
        invoices = []

    payments = list(customer.payments.all()) if hasattr(customer, "payments") else list(Payment.objects.filter(customer=customer))

    entries = []

    def _get_invoice_amount(inv):
        for fld in ("grand_total", "total", "amount", "invoice_total"):
            if hasattr(inv, fld):
                try:
                    return Decimal(str(getattr(inv, fld) or 0))
                except Exception:
                    return Decimal("0.00")
        try:
            return Decimal(str(getattr(inv, "amount", 0) or 0))
        except Exception:
            return Decimal("0.00")

    for inv in invoices:
        amt = _get_invoice_amount(inv)
        date_raw = getattr(inv, "date", None) or getattr(inv, "order_date", None) or getattr(inv, "date_added", None)
        entries.append({
            "type": "invoice",
            "date_raw": date_raw,
            "date_norm": _get_date_norm(inv),
            "amount": amt,
            "obj": inv,
            "description": getattr(inv, "description", "") or getattr(inv, "notes", "") or f"Invoice #{getattr(inv, 'pk', '')}",
        })

    for p in payments:
        try:
            amt = Decimal(str(getattr(p, "amount", 0) or 0))
        except Exception:
            amt = Decimal("0.00")
        date_raw = getattr(p, "date", None)
        entries.append({
            "type": "payment",
            "date_raw": date_raw,
            "date_norm": _get_date_norm(p),
            "amount": amt,
            "obj": p,
            "description": getattr(p, "remarks", "") or getattr(p, "cheque_number", "") or f"Payment #{getattr(p, 'pk', '')}",
        })

    entries.sort(key=lambda e: e["date_norm"] or timezone.make_aware(_dt.datetime(1970, 1, 1), tz))

    running = Decimal("0.00")
    ledger_rows = []
    for e in entries:
        if e["type"] == "invoice":
            running += e["amount"]
            change = e["amount"]
        else:
            running -= e["amount"]
            change = -e["amount"]

        display_date = e.get("date_raw") or e.get("date_norm")
        ledger_rows.append({
            "date": display_date,
            "type": e["type"],
            "amount": e["amount"],
            "change": change,
            "running_balance": running,
            "description": e.get("description"),
            "obj": e.get("obj"),
        })

    total_invoiced = sum((r["amount"] for r in ledger_rows if r["type"] == "invoice"), Decimal("0.00"))
    total_paid = sum((r["amount"] for r in ledger_rows if r["type"] == "payment"), Decimal("0.00"))
    balance = total_invoiced - total_paid

    context = {
        "customer": customer,
        "ledger_rows": ledger_rows,
        "balance": balance,
        "total_invoiced": total_invoiced,
        "total_paid": total_paid,
    }
    return render(request, "accounts/customer_ledger.html", context)
