# UTF-8
"""
Inventory-focused views. Phase-1: product-level stock (Item.stock) is used for
inventory UI and totals. Per-color / ProductVariant functionality is retained
in dedicated manage_product_colors view (not linked from create/update flow).
"""
import random
import string
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.db import transaction
from django.db.models import Q, Count, Sum
from django.db.models.functions import TruncMonth
from django.contrib import messages
from .db_backup import create_backup, list_backups, restore_backup
from django.utils.text import slugify

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin

from django.views.generic import (
    DetailView, CreateView, UpdateView, DeleteView, ListView
)
from django.views.generic.edit import FormMixin

from django_tables2 import SingleTableView
import django_tables2 as tables
from django_tables2.export.views import ExportMixin

from accounts.models import Profile, Vendor
from transactions.models import Sale
from .models import Category, Item, Delivery, ProductVariant, Color
from .forms import ItemForm, CategoryForm, DeliveryForm, ItemFilterForm, ColorForm
from .tables import ItemTable


# ----------------------------------------------------------------------
# Helper: Unique SKU Generator (kept for manage_product_colors)
# ----------------------------------------------------------------------
def generate_unique_sku(product, color, max_attempts=20):
    base = (
        f"{slugify(product.slug or product.name)[:30].upper()}-"
        f"{slugify(color.slug or color.name)[:10].upper()}"
    )
    sku = base
    attempts = 0
    while ProductVariant.objects.filter(sku=sku).exists():
        attempts += 1
        suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=3))
        sku = f"{base}-{suffix}"
        if attempts >= max_attempts:
            sku = f"{base}-{product.pk}-{suffix}"
            break
    return sku


# ----------------------------------------------------------------------
# AJAX endpoint: search / list items (used by invoice UI and inventory autocomplete)
# Uses Item.stock as the source of truth for inventory totals.
# ----------------------------------------------------------------------
@require_GET
def get_items_ajax_view(request):
    q = (request.GET.get("q") or "").strip()
    limit = request.GET.get("limit")
    try:
        limit = int(limit) if limit is not None else 50
    except (ValueError, TypeError):
        limit = 50

    qs = Item.objects.all().select_related("category").order_by("name")
    if q:
        terms = [t.strip() for t in q.split() if t.strip()]
        for t in terms:
            qs = qs.filter(name__icontains=t)

    qs = qs[:limit]

    out = []
    for it in qs:
        # Prefer product-level stock; fallback to variant sum if necessary
        total_stock = int(it.stock or 0)
        if total_stock == 0:
            # fallback to variant sum so pre-migration UI isn't empty
            agg = it.variants.aggregate(total=Sum('stock_qty')) if hasattr(it, 'variants') else {}
            total_stock = int(agg.get('total') or 0)
        cat = it.category.name if getattr(it, "category", None) else ""
        display = f"{it.name} ({cat}) - Total Stock: {total_stock}"
        out.append({
            "id": it.pk,
            "name": it.name,
            "category": cat,
            "total_stock": total_stock,
            "display_name": display,
        })

    return JsonResponse(out, safe=False)


# ----------------------------------------------------------------------
# Dashboard
# ----------------------------------------------------------------------
@login_required
def dashboard(request):
    from datetime import date, datetime, timedelta
    from django.db.models import Sum, Count, Q
    from django.db.models.functions import TruncMonth
    from invoice.models import Invoice
    from accounts.models import Customer
    from transactions.models import Purchase

    today = datetime.today().date()
    first_of_this_month = today.replace(day=1)
    if first_of_this_month.month == 1:
        first_of_last_month = first_of_this_month.replace(year=first_of_this_month.year - 1, month=12)
    else:
        first_of_last_month = first_of_this_month.replace(month=first_of_this_month.month - 1)

    # ── Stat Cards ────────────────────────────────────────────────

    # Revenue: sum of invoice grand_totals
    revenue_this_month = Invoice.objects.filter(
        date__date__gte=first_of_this_month
    ).aggregate(t=Sum('grand_total'))['t'] or 0

    revenue_last_month = Invoice.objects.filter(
        date__date__gte=first_of_last_month,
        date__date__lt=first_of_this_month,
    ).aggregate(t=Sum('grand_total'))['t'] or 0

    revenue_change = None
    if revenue_last_month:
        revenue_change = round(((revenue_this_month - revenue_last_month) / revenue_last_month) * 100)

    # Total outstanding balance across all customers
    total_outstanding = Customer.objects.aggregate(t=Sum('balance'))['t'] or 0

    # Purchases this month
    purchases_this_month = Purchase.objects.filter(
        order_date__date__gte=first_of_this_month
    ).aggregate(t=Sum('total_value'))['t'] or 0

    purchases_last_month = Purchase.objects.filter(
        order_date__date__gte=first_of_last_month,
        order_date__date__lt=first_of_this_month,
    ).aggregate(t=Sum('total_value'))['t'] or 0

    purchases_change = None
    if purchases_last_month:
        purchases_change = round(((purchases_this_month - purchases_last_month) / purchases_last_month) * 100)

    # Product counts
    product_count = Item.objects.count()
    total_stock = Item.objects.aggregate(t=Sum('stock'))['t'] or 0
    low_stock_count = Item.objects.filter(stock__gt=0, stock__lte=10).count()
    out_of_stock_count = Item.objects.filter(stock=0).count()

    # Invoices this month
    invoices_this_month = Invoice.objects.filter(date__date__gte=first_of_this_month).count()
    invoices_total = Invoice.objects.count()

    # Staff / customers
    profiles_count = Profile.objects.count()
    customers_count = Customer.objects.count()

    # ── Revenue vs Purchases chart (last 12 months) ───────────────
    start_month = (today.replace(day=1) - timedelta(days=365)).replace(day=1)

    inv_qs = (
        Invoice.objects
        .filter(date__date__gte=start_month)
        .annotate(month=TruncMonth('date'))
        .values('month')
        .annotate(total=Sum('grand_total'))
        .order_by('month')
    )
    inv_map = {}
    for r in inv_qs:
        m = r['month']
        if isinstance(m, datetime):
            m = m.date().replace(day=1)
        else:
            m = m.replace(day=1)
        inv_map[m] = float(r['total'] or 0)

    pur_qs = (
        Purchase.objects
        .filter(order_date__date__gte=start_month)
        .annotate(month=TruncMonth('order_date'))
        .values('month')
        .annotate(total=Sum('total_value'))
        .order_by('month')
    )
    pur_map = {}
    for r in pur_qs:
        m = r['month']
        if isinstance(m, datetime):
            m = m.date().replace(day=1)
        else:
            m = m.replace(day=1)
        pur_map[m] = float(r['total'] or 0)

    chart_labels, chart_revenue, chart_purchases = [], [], []
    cur = start_month
    while cur <= today.replace(day=1):
        chart_labels.append(cur.strftime('%b %Y'))
        chart_revenue.append(inv_map.get(cur, 0.0))
        chart_purchases.append(pur_map.get(cur, 0.0))
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)

    # ── Category distribution (for doughnut) ─────────────────────
    category_counts_qs = Category.objects.annotate(item_count=Count('item')).values('name', 'item_count')
    categories = [c['name'] for c in category_counts_qs]
    category_counts = [c['item_count'] for c in category_counts_qs]

    # ── Top 5 customers by outstanding balance ────────────────────
    top_customers = Customer.objects.filter(balance__gt=0).order_by('-balance')[:5]

    # ── Recent 5 invoices ─────────────────────────────────────────
    recent_invoices = Invoice.objects.select_related('customer').order_by('-date')[:5]

    # ── Low stock items ───────────────────────────────────────────
    low_stock_items = Item.objects.filter(stock__gt=0, stock__lte=10).select_related('category').order_by('stock')[:8]

    # ── Store stock breakdown (if locations app is set up) ────────
    try:
        from locations.models import StoreStock, Store
        store_stock_data = (
            StoreStock.objects
            .values('store__name', 'store__region__company')
            .annotate(total=Sum('quantity'))
            .order_by('-total')
        )
        store_labels = [f"{r['store__name']}" for r in store_stock_data]
        store_values = [r['total'] for r in store_stock_data]
        store_companies = [r['store__region__company'] for r in store_stock_data]
    except Exception:
        store_labels, store_values, store_companies = [], [], []

    context = {
        # cards
        'product_count': product_count,
        'profiles_count': profiles_count,
        'customers_count': customers_count,
        'total_stock': total_stock,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'invoices_this_month': invoices_this_month,
        'invoices_total': invoices_total,
        'revenue_this_month': revenue_this_month,
        'revenue_last_month': revenue_last_month,
        'revenue_change': revenue_change,
        'purchases_this_month': purchases_this_month,
        'purchases_change': purchases_change,
        'total_outstanding': total_outstanding,
        # charts
        'chart_labels': chart_labels,
        'chart_revenue': chart_revenue,
        'chart_purchases': chart_purchases,
        'categories': categories,
        'category_counts': category_counts,
        'store_labels': store_labels,
        'store_values': store_values,
        'store_companies': store_companies,
        # tables
        'top_customers': top_customers,
        'recent_invoices': recent_invoices,
        'low_stock_items': low_stock_items,
        # legacy (keep for any other templates that reference these)
        'items': Item.objects.all(),
        'profiles': Profile.objects.all(),
        'vendors': Vendor.objects.all(),
        'delivery': Delivery.objects.all(),
        'sales': Sale.objects.all(),
        'items_count': product_count,
        'sale_dates_labels': chart_labels,
        'sale_dates_values': chart_revenue,
    }
    return render(request, 'store/dashboard.html', context)


# ----------------------------------------------------------------------
# Product List + Filtering (inventory uses product-level stock)
# ----------------------------------------------------------------------
class ProductListView(LoginRequiredMixin, ExportMixin, tables.SingleTableView):
    model = Item
    table_class = ItemTable
    template_name = "store/productslist.html"
    context_object_name = "items"
    paginate_by = None

    def get_queryset(self):
        qs = super().get_queryset().select_related("category", "vendor")
        q = self.request.GET.get("q") or ""
        category_id = self.request.GET.get("category")
        in_stock = self.request.GET.get("in_stock")

        if q:
            for p in q.split():
                qs = qs.filter(name__icontains=p)

        if category_id:
            qs = qs.filter(category_id=category_id)

        if in_stock:
            qs = qs.filter(stock__gt=0)

        return qs.order_by("id")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filter_form"] = ItemFilterForm(self.request.GET or None)
        ctx["total_items"] = Item.objects.aggregate(Sum("stock")).get("stock__sum", 0) or 0
        return ctx


class ItemSearchListView(ProductListView):
    pass


# ----------------------------------------------------------------------
# Product Views
# ----------------------------------------------------------------------
class ProductDetailView(LoginRequiredMixin, FormMixin, DetailView):
    model = Item
    template_name = "store/productdetail.html"

    def get_success_url(self):
        return reverse("product-detail", kwargs={"slug": self.object.slug})


class ProductCreateView(LoginRequiredMixin, CreateView):
    model = Item
    template_name = "store/productcreate.html"
    form_class = ItemForm

    def get_success_url(self):
        # Phase-1: go back to products list (do not force manage-product-colors)
        return reverse("productslist")


class ProductUpdateView(LoginRequiredMixin, UpdateView):
    model = Item
    template_name = "store/productupdate.html"
    form_class = ItemForm
    success_url = reverse_lazy("productslist")


class ProductDeleteView(LoginRequiredMixin, DeleteView):
    model = Item
    template_name = "store/productdelete.html"
    success_url = reverse_lazy("productslist")

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        item = self.object

        # delete variants if present (safe cleanup)
        try:
            item.variants.all().delete()
        except Exception:
            pass

        # Other related cleanup (best-effort)
        for rel in item._meta.get_fields():
            if rel.one_to_many and rel.auto_created:
                related_manager = getattr(item, rel.get_accessor_name(), None)
                if related_manager:
                    try:
                        related_manager.all().delete()
                    except Exception:
                        pass
            if rel.one_to_one and rel.auto_created:
                related_obj = getattr(item, rel.get_accessor_name(), None)
                if related_obj:
                    try:
                        related_obj.delete()
                    except Exception:
                        pass
            if rel.many_to_many and rel.auto_created:
                related_manager = getattr(item, rel.get_accessor_name(), None)
                if related_manager:
                    try:
                        related_manager.clear()
                    except Exception:
                        pass

        return super().delete(request, *args, **kwargs)


# ----------------------------------------------------------------------
# Category views
# ----------------------------------------------------------------------
from django.views.generic import ListView  # already imported above but keep for clarity

class CategoryListView(LoginRequiredMixin, ListView):
    model = Category
    template_name = "store/categorieslist.html"
    context_object_name = "categories"
    paginate_by = None
    ordering = ["name"]

    def get_queryset(self):
        return super().get_queryset().order_by("name")


class CategoryDetailView(LoginRequiredMixin, DetailView):
    model = Category
    template_name = "store/categorydetail.html"
    context_object_name = "category"


class CategoryCreateView(LoginRequiredMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = "store/category_form.html"
    success_url = reverse_lazy("category-list")


class CategoryUpdateView(LoginRequiredMixin, UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = "store/category_form.html"
    success_url = reverse_lazy("category-list")


class CategoryDeleteView(LoginRequiredMixin, DeleteView):
    model = Category
    template_name = "store/category_confirm_delete.html"
    success_url = reverse_lazy("category-list")


# ----------------------------------------------------------------------
# MANAGE COLORS (Per-Color Stock) - kept as an isolated management endpoint
# Note: not linked from create/update flows in Phase-1
# ----------------------------------------------------------------------
@login_required
def manage_product_colors(request, pk):
    """
    Keep this endpoint so you can still manage per-color stock manually if needed.
    It's no longer the primary inventory UI in Phase-1.
    """
    product = get_object_or_404(Item, pk=pk)

    desired_names = [
        "Piano black",
        "Piano white",
        "Piano grey",
        "Piano golden",
        "Piano olive",
        "Atlantic grey",
        "Atlantic brown",
        "Atlantic pearl white",
    ]

    for name in desired_names:
        Color.objects.get_or_create(name=name)

    desired_map = {c.name: c for c in Color.objects.filter(name__in=desired_names)}
    color_objs = []
    for n in desired_names:
        c = desired_map.get(n)
        if c:
            color_objs.append(c)

    others = Color.objects.exclude(name__in=desired_names).order_by("name")
    color_objs.extend(list(others))

    variant_map = {v.color_id: v for v in product.variants.all()}

    if request.method == "POST":
        for color in color_objs:
            raw_stock = request.POST.get(f"stock_{color.id}") or "0"
            try:
                stock_qty = int(raw_stock)
            except ValueError:
                stock_qty = 0
            stock_qty = max(stock_qty, 0)
            if stock_qty > 0:
                variant = variant_map.get(color.id)
                if variant:
                    variant.stock_qty = stock_qty
                    variant.save(update_fields=["stock_qty"])
                else:
                    sku = generate_unique_sku(product, color)
                    ProductVariant.objects.create(
                        product=product, color=color, sku=sku, stock_qty=stock_qty
                    )
            else:
                if color.id in variant_map:
                    variant_map[color.id].delete()

        # Optionally: update aggregated product.stock if you want immediate sync
        # product.stock = product.total_stock()  # but not automatic here
        # product.save(update_fields=['stock'])

        return redirect("productslist")

    return render(
        request,
        "store/manage_colors.html",
        {"product": product, "colors": color_objs, "variants": variant_map},
    )


# ----------------------------------------------------------------------
# color_create_ajax: create a Color via AJAX (used by Manage Colors page)
# ----------------------------------------------------------------------
@login_required
@require_POST
def color_create_ajax(request):
    form = ColorForm(request.POST)
    if form.is_valid():
        color = form.save()
        return JsonResponse({"success": True, "id": color.id, "name": color.name})
    return JsonResponse({"success": False, "errors": form.errors}, status=400)


# ----------------------------------------------------------------------
# Delivery Views (unchanged)
# ----------------------------------------------------------------------
class DeliveryListView(LoginRequiredMixin, ExportMixin, tables.SingleTableView):
    model = Delivery
    paginate_by = 10
    template_name = "store/deliveries.html"
    context_object_name = "deliveries"

    def get_queryset(self):
        return super().get_queryset().order_by("-created_at") if hasattr(self.model, "created_at") else super().get_queryset()


class DeliveryDetailView(LoginRequiredMixin, DetailView):
    model = Delivery
    template_name = "store/deliverydetail.html"
    context_object_name = "delivery"


class DeliveryCreateView(LoginRequiredMixin, CreateView):
    model = Delivery
    form_class = DeliveryForm
    template_name = "store/deliverycreate.html"
    success_url = reverse_lazy("deliveries")


class DeliveryUpdateView(LoginRequiredMixin, UpdateView):
    model = Delivery
    form_class = DeliveryForm
    template_name = "store/deliveryupdate.html"
    success_url = reverse_lazy("deliveries")


class DeliveryDeleteView(LoginRequiredMixin, DeleteView):
    model = Delivery
    template_name = "store/deliverydelete.html"
    success_url = reverse_lazy("deliveries")

# Backup / Restore views (placed in store/views.py)

from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

@login_required
@require_POST
def create_db_backup(request):
    """
    POST-only endpoint — creates a backup and keeps only the latest MAX_BACKUPS.
    Redirects back to dashboard with a message.
    """
    try:
        name = create_backup()
        messages.success(request, f"Backup created: {name}")
    except Exception as e:
        messages.error(request, f"Backup failed: {e}")
    return redirect("dashboard")


@login_required
def restore_db_backup(request):
    """
    GET: show list of backups
    POST: restore selected backup (overwrites current DB)
    """
    if request.method == "POST":
        fname = request.POST.get("backup")
        if not fname:
            messages.error(request, "No backup selected.")
            return redirect("restore_db_backup")

        # Optional: make a quick automatic backup of current DB before restore
        try:
            # auto backup current DB before overwrite
            create_backup()
            restore_backup(fname)
            messages.success(request, f"Restored backup: {fname}")
        except Exception as e:
            messages.error(request, f"Restore failed: {e}")
        return redirect("dashboard")

    # GET
    backups = list_backups()
    return render(request, "store/restore_backup.html", {"backups": backups})
