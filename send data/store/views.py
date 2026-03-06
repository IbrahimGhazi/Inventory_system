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
    profiles = Profile.objects.all()
    items = Item.objects.all()

    product_count = items.count()
    items_count = product_count
    profiles_count = profiles.count()

    # total physical stock across all products (product-level stock)
    total_stock = Item.objects.aggregate(total=Sum("stock")).get("total", 0) or 0

    # categories + counts
    category_counts_qs = Category.objects.annotate(item_count=Count("item")).values(
        "name", "item_count"
    )
    categories = [cat["name"] for cat in category_counts_qs]
    category_counts = [cat["item_count"] for cat in category_counts_qs]

    # sales aggregation for last 12 months
    from datetime import date, datetime, timedelta
    today = datetime.today().date()
    start_month = (today.replace(day=1) - timedelta(days=365)).replace(day=1)

    sales_qs = (
        Sale.objects.filter(date_added__date__gte=start_month)
        .annotate(month=TruncMonth("date_added"))
        .values("month")
        .annotate(month_total=Sum("grand_total"))
        .order_by("month")
    )

    sales_map = {}
    for s in sales_qs:
        month_dt = s["month"]
        if isinstance(month_dt, datetime):
            month_dt = month_dt.date().replace(day=1)
        else:
            month_dt = month_dt.replace(day=1)
        sales_map[month_dt] = float(s.get("month_total") or 0.0)

    labels = []
    values = []
    current = start_month
    while current <= today.replace(day=1):
        labels.append(current.strftime("%b %Y"))
        values.append(sales_map.get(current, 0.0))
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    context = {
        "items": items,
        "profiles": profiles,
        "profiles_count": profiles_count,
        "items_count": items_count,
        "product_count": product_count,
        "total_stock": total_stock,
        "vendors": Vendor.objects.all(),
        "delivery": Delivery.objects.all(),
        "sales": Sale.objects.all(),
        "categories": categories,
        "category_counts": category_counts,
        "sale_dates_labels": labels,
        "sale_dates_values": values,
    }
    return render(request, "store/dashboard.html", context)


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
