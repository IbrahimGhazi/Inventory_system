# transactions/views.py
import json
import logging
from decimal import Decimal

from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction as db_transaction
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import DetailView, ListView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.views import View

from .models import Sale, SaleDetail, Purchase, PurchaseDetail
from .forms import SaleForm, PurchaseForm
from store.models import Item, ProductVariant, Color, Category
from accounts.models import Customer, Vendor

logger = logging.getLogger(__name__)


# -------------------- EXPORTS --------------------

def export_sales_to_excel(request):
    try:
        from openpyxl import Workbook
    except Exception:
        return HttpResponse("openpyxl not installed", status=500)

    wb = Workbook()
    ws = wb.active
    ws.title = "Sales"
    ws.append(["Sale ID", "Customer", "Date", "Sub Total", "Grand Total"])

    for s in Sale.objects.all().order_by("-date_added")[:500]:
        ws.append([
            s.pk,
            getattr(s.customer, "get_full_name", lambda: "")(),
            s.date_added.strftime("%Y-%m-%d %H:%M") if s.date_added else "",
            s.sub_total,
            s.grand_total
        ])

    resp = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    resp["Content-Disposition"] = "attachment; filename=sales.xlsx"
    wb.save(resp)
    return resp


def export_purchases_to_excel(request):
    try:
        from openpyxl import Workbook
    except Exception:
        return HttpResponse("openpyxl not installed", status=500)

    wb = Workbook()
    ws = wb.active
    ws.title = "Purchases"
    ws.append(["Purchase ID", "Vendor", "Order Date", "Total Value"])

    for p in Purchase.objects.all().order_by("-order_date")[:500]:
        ws.append([
            p.pk,
            getattr(p.vendor, "name", ""),
            p.order_date.strftime("%Y-%m-%d %H:%M") if p.order_date else "",
            p.total_value
        ])

    resp = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    resp["Content-Disposition"] = "attachment; filename=purchases.xlsx"
    wb.save(resp)
    return resp


# -------------------- SALES --------------------

class SaleListView(LoginRequiredMixin, ListView):
    model = Sale
    template_name = "transactions/sales_list.html"
    context_object_name = "sales"
    paginate_by = 10
    ordering = ["-date_added"]


class SaleDetailView(LoginRequiredMixin, DetailView):
    model = Sale
    template_name = "transactions/sale_detail.html"


class SaleCreateView(LoginRequiredMixin, View):

    def get(self, request, *args, **kwargs):
        return render(request, "transactions/sale_create.html", {
            "form": SaleForm()
        })

    def post(self, request, *args, **kwargs):
        ct = request.content_type or ""
        is_ajax = ct.startswith("application/json") or \
                  request.headers.get("x-requested-with") == "XMLHttpRequest"

        if not is_ajax:
            return redirect(reverse("saleslist"))

        payload = json.loads(request.body.decode("utf-8"))
        customer = get_object_or_404(Customer, pk=payload.get("customer_id"))

        try:
            with db_transaction.atomic():
                sale = Sale.objects.create(
                    customer=customer,
                    sub_total=Decimal("0.00"),
                    grand_total=Decimal("0.00"),
                )

                total = Decimal("0.00")
                for ln in payload.get("items", []):
                    item = get_object_or_404(Item, pk=ln["item_id"])
                    qty = int(ln["quantity"])
                    price = Decimal(str(ln["price"]))
                    line_total = qty * price

                    SaleDetail.objects.create(
                        sale=sale,
                        item=item,
                        quantity=qty,
                        price=price,
                        total_detail=line_total
                    )

                    total += line_total

                sale.sub_total = total
                sale.grand_total = total
                sale.save(update_fields=["sub_total", "grand_total"])

            return JsonResponse({"status": "success", "redirect": reverse("saleslist")})

        except Exception as e:
            logger.exception("Sale creation failed")
            return JsonResponse({"status": "error", "message": str(e)}, status=400)


def sale_create_view(request):
    return SaleCreateView.as_view()(request)


class SaleDeleteView(LoginRequiredMixin, DeleteView):
    model = Sale
    template_name = "transactions/saledelete.html"

    def get_success_url(self):
        return reverse("saleslist")


# -------------------- PURCHASES --------------------

class PurchaseListView(LoginRequiredMixin, ListView):
    model = Purchase
    template_name = "transactions/purchases_list.html"
    context_object_name = "purchases"
    paginate_by = 15
    ordering = ["-order_date"]


class PurchaseDetailView(LoginRequiredMixin, DetailView):
    model = Purchase
    template_name = "transactions/purchase_detail.html"


class PurchaseCreateView(LoginRequiredMixin, CreateView):
    model = Purchase
    form_class = PurchaseForm
    template_name = "transactions/purchases_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        items_qs = Item.objects.select_related("category").order_by("name").values(
            "id",
            "name",
            "price",
            "stock",
            "category_id",
            "category__name",
        )

        ctx["items"] = [
            {
                "id": i["id"],
                "name": i["name"],
                "price": float(i["price"] or 0),
                "stock": int(i["stock"] or 0),
                "category_id": i["category_id"],
                "category_name": i["category__name"],
            }
            for i in items_qs
        ]

        ctx["categories"] = list(
            Category.objects.all().values("id", "name")
        )

        ctx["existing_lines"] = []
        return ctx

    def form_valid(self, form):
        purchase = form.save(commit=False)
        purchase.delivery_status = "S"

        details = json.loads(self.request.POST.get("details_json", "[]"))

        try:
            with db_transaction.atomic():
                purchase.save()

                total = Decimal("0.00")
                for ln in details:
                    item = get_object_or_404(Item, pk=ln["item_id"])
                    qty = int(ln["quantity"])
                    price = Decimal(str(ln["price"]))
                    line_total = qty * price

                    PurchaseDetail.objects.create(
                        purchase=purchase,
                        item=item,
                        quantity=qty,
                        price=price,
                        total_detail=line_total
                    )

                    total += line_total

                purchase.total_value = total
                purchase.save(update_fields=["total_value"])

            return redirect("purchaseslist")

        except Exception as e:
            logger.exception("Purchase creation failed")
            return JsonResponse({"status": "error", "message": str(e)}, status=400)


class PurchaseUpdateView(LoginRequiredMixin, UpdateView):
    model = Purchase
    form_class = PurchaseForm
    template_name = "transactions/purchases_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        items_qs = Item.objects.select_related("category").order_by("name").values(
            "id",
            "name",
            "price",
            "stock",
            "category_id",
            "category__name",
        )

        ctx["items"] = [
            {
                "id": i["id"],
                "name": i["name"],
                "price": float(i["price"] or 0),
                "stock": int(i["stock"] or 0),
                "category_id": i["category_id"],
                "category_name": i["category__name"],
            }
            for i in items_qs
        ]

        ctx["categories"] = list(
            Category.objects.all().values("id", "name")
        )

        ctx["existing_lines"] = list(
            self.object.purchase_details.values("item_id", "quantity", "price")
        )

        return ctx

    def form_valid(self, form):
        purchase = form.save(commit=False)
        details = json.loads(self.request.POST.get("details_json", "[]"))

        try:
            with db_transaction.atomic():
                purchase.save()
                purchase.purchase_details.all().delete()

                total = Decimal("0.00")
                for ln in details:
                    item = get_object_or_404(Item, pk=ln["item_id"])
                    qty = int(ln["quantity"])
                    price = Decimal(str(ln["price"]))
                    line_total = qty * price

                    PurchaseDetail.objects.create(
                        purchase=purchase,
                        item=item,
                        quantity=qty,
                        price=price,
                        total_detail=line_total
                    )

                    total += line_total

                purchase.total_value = total
                purchase.save(update_fields=["total_value"])

            return JsonResponse({"status": "success", "redirect": reverse("purchaseslist")})

        except Exception as e:
            logger.exception("Purchase update failed")
            return JsonResponse({"status": "error", "message": str(e)}, status=400)


class PurchaseDeleteView(LoginRequiredMixin, DeleteView):
    model = Purchase
    template_name = "transactions/purchasedelete.html"

    def get_success_url(self):
        return reverse("purchaseslist")
