# invoice/views.py
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import os
import logging
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.shortcuts import redirect, render
from django.http import HttpResponse, JsonResponse
from django.views.generic import DetailView, CreateView, UpdateView, DeleteView
from django.contrib import messages
from django_tables2 import SingleTableView
from django_tables2.export.views import ExportMixin
from django.views.decorators.http import require_GET
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models.signals import post_save, post_delete
from django.db.models import Sum
from django.conf import settings

from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import black, HexColor, Color

from .models import Invoice, InvoiceItem
from .tables import InvoiceTable
from .forms import InvoiceForm, InvoiceItemFormSet

from store.models import Item

logger = logging.getLogger(__name__)


# -------------------- helpers --------------------
def _to_decimal(value):
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


def _build_counts_from_queryset(qs):
    counts = {}
    for r in qs:
        key = (getattr(r, "item_id", None),)
        qty = _to_decimal(getattr(r, "quantity", 0))
        counts[key] = counts.get(key, Decimal("0.00")) + qty
    return counts


def _build_counts_from_formset(formset):
    counts = {}
    for f in formset.forms:
        if not hasattr(f, "cleaned_data"):
            continue
        cd = f.cleaned_data
        if cd.get("DELETE"):
            continue
        item = cd.get("item")
        qty = _to_decimal(cd.get("quantity", 0))
        key = (item.pk if item else None,)
        counts[key] = counts.get(key, Decimal("0.00")) + qty
    return counts


# -------------------- simple APIs --------------------
@require_GET
def api_item_colors(request, pk):
    try:
        item = Item.objects.get(pk=pk)
    except ObjectDoesNotExist:
        return JsonResponse({"error": "Item not found"}, status=404)

    stock = int(item.stock or 0)
    data = [{"id": None, "name": "Default", "stock": stock}]
    return JsonResponse(data, safe=False)


@require_GET
def api_item_price(request, pk):
    try:
        item = Item.objects.get(pk=pk)
    except ObjectDoesNotExist:
        return JsonResponse({"error": "Item not found"}, status=404)
    price = Decimal(item.price or 0).quantize(Decimal("0.01"))
    return JsonResponse({"price": f"{price:.2f}"})
@require_GET
def api_items_for_store(request):
    """Return items that have stock in the given store."""
    store_id = request.GET.get('store_id')
    if not store_id:
        # no store selected — return all items
        items = Item.objects.order_by('name')
        data = [
            {
                'id': it.pk,
                'name': it.name,
                'price': str(it.price or '0.00'),
                'stock': int(it.stock or 0),
                'category': it.category.name if it.category else '',
            }
            for it in items
        ]
        return JsonResponse(data, safe=False)

    from locations.models import StoreStock
    qs = (
        StoreStock.objects
        .filter(store_id=store_id, quantity__gt=0)
        .select_related('item', 'item__category')
        .order_by('item__name')
    )
    data = [
        {
            'id': ss.item.pk,
            'name': ss.item.name,
            'price': str(ss.item.price or '0.00'),
            'stock': ss.quantity,           # store-specific stock
            'category': ss.item.category.name if ss.item.category else '',
        }
        for ss in qs
    ]
    return JsonResponse(data, safe=False)


# -------------------- list view --------------------
class InvoiceListView(ExportMixin, SingleTableView):
    model = Invoice
    table_class = InvoiceTable
    template_name = "invoice/invoicelist.html"
    context_object_name = "invoices"
    paginate_by = 10
    table_pagination = False

    def get_queryset(self):
        qs = (
            Invoice.objects
            .select_related("customer")
            .prefetch_related("items__item")
            .order_by("-date")
        )

        invoice_id = self.request.GET.get("invoice_id", "").strip()

        if invoice_id:
            try:
                qs = qs.filter(pk=int(invoice_id))
            except ValueError:
                qs = qs.filter(uuid__iexact=invoice_id)

        return qs


# -------------------- improved PDF detail view --------------------
class ImprovedInvoiceDetailView(DetailView):
    model = Invoice
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"

    def get_object(self, queryset=None):
        uuid = self.kwargs.get("uuid")
        return get_object_or_404(Invoice, uuid=uuid)

    def get(self, request, *args, **kwargs):
        invoice = self.get_object()
        customer = invoice.customer
        items = invoice.items.all()

        prev_invoices_total = (
            customer.invoices.filter(date__lt=invoice.date)
            .aggregate(total=Sum("grand_total"))
            .get("total") or Decimal("0.00")
        )
        prev_payments_total = (
            customer.payments.filter(date__lte=invoice.date)
            .aggregate(total=Sum("amount"))
            .get("total") or Decimal("0.00")
        )

        opening_balance = (prev_invoices_total - prev_payments_total).quantize(Decimal("0.01"))
        closing_balance = (opening_balance + invoice.grand_total).quantize(Decimal("0.01"))

        response = HttpResponse(content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="Invoice_{invoice.id}.pdf"'

        PAGE_WIDTH = 137 * mm
        PAGE_HEIGHT = 195 * mm
        p = canvas.Canvas(response, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))

        LOGO_PATH = os.path.join(settings.BASE_DIR, "static", "images", "lenter_logo.png")
        SHOP_NAME = "AL MADINA ENTERPRISE"
        SHOP_META = "Karachi, Pakistan | +92 335 0040521"

        PRIMARY = HexColor("#0e4b66")
        ACCENT = HexColor("#2d9cdb")
        SUCCESS = HexColor("#27ae60")
        TEXT = black
        MUTED = Color(0.25, 0.25, 0.25)
        LIGHT_GRAY = Color(0.96, 0.96, 0.96)
        BORDER = Color(0.88, 0.88, 0.88)

        TITLE_FONT = ("Helvetica-Bold", 20)
        SHOP_FONT = ("Helvetica-Bold", 13)
        META_FONT = ("Helvetica", 8)
        HEADER_FONT = ("Helvetica-Bold", 8.5)
        BODY_FONT = ("Helvetica", 8.5)
        NUM_FONT = ("Helvetica-Bold", 8.5)
        LABEL_FONT = ("Helvetica", 9)

        LEFT = -2 * mm
        RIGHT = TOP = BOTTOM = 0 * mm

        def money_fmt(val):
            try:
                return f"{Decimal(val):,.2f}"
            except Exception:
                return "0.00"

        def wrap_text(text, font, size, width, max_lines=None):
            if not text:
                return []
            words = str(text).split()
            lines, cur = [], ""
            for w in words:
                test = (cur + " " + w).strip()
                if p.stringWidth(test, font, size) <= width:
                    cur = test
                else:
                    if cur:
                        lines.append(cur)
                        if max_lines and len(lines) >= max_lines:
                            return lines
                    cur = w
            if cur:
                lines.append(cur)
            return lines[:max_lines] if max_lines else lines

        def draw_header(y):
            try:
                if os.path.exists(LOGO_PATH):
                    p.drawImage(
                        ImageReader(LOGO_PATH),
                        LEFT + 2 * mm,
                        y - 15 * mm,
                        width=26 * mm,
                        height=16 * mm,
                        preserveAspectRatio=True,
                        mask="auto",
                    )
            except Exception as ex:
                logger.debug("Logo error: %s", ex)

            p.setFont(*SHOP_FONT)
            p.setFillColor(PRIMARY)
            p.drawCentredString(PAGE_WIDTH / 2, y - 2 * mm, SHOP_NAME)

            p.setFont(*META_FONT)
            p.setFillColor(MUTED)
            p.drawCentredString(PAGE_WIDTH / 2, y - 8 * mm, SHOP_META)

            title_y = y - 15 * mm
            p.setFillColor(PRIMARY)
            p.rect(LEFT, title_y - 2 * mm, PAGE_WIDTH - LEFT - RIGHT, 7 * mm, stroke=0, fill=1)

            p.setFillColor(ACCENT)
            p.rect(LEFT, title_y - 2 * mm, 3 * mm, 7 * mm, stroke=0, fill=1)
            p.rect(PAGE_WIDTH - RIGHT - 3 * mm, title_y - 2 * mm, 3 * mm, 7 * mm, stroke=0, fill=1)

            p.setFont(*TITLE_FONT)
            p.setFillColor(Color(1, 1, 1))
            p.drawCentredString(PAGE_WIDTH / 2, title_y - 1.5 * mm, "INVOICE")

            p.setFillColor(TEXT)
            return title_y - 10 * mm

        y = draw_header(PAGE_HEIGHT - TOP - 10 * mm)

        bill_y = y + 5 * mm
        left_x = LEFT + 3 * mm

        p.setFont("Helvetica-Bold", 10)
        p.setFillColor(PRIMARY)
        p.drawString(left_x, bill_y, "BILL TO")
        p.setLineWidth(1.5)
        p.setStrokeColor(ACCENT)
        p.line(left_x, bill_y - 1.2 * mm, left_x + 18 * mm, bill_y - 1.2 * mm)
        p.setFillColor(TEXT)

        name = getattr(customer, "name", str(customer))
        p.setFillColor(LIGHT_GRAY)
        p.roundRect(left_x - 1 * mm, bill_y - 7 * mm, 60 * mm, 6 * mm, 1.5 * mm, stroke=0, fill=1)

        p.setFont("Helvetica-Bold", 10)
        p.setFillColor(TEXT)
        p.drawString(left_x, bill_y - 6 * mm, name)

        p.setFont(*LABEL_FONT)
        cur_y = bill_y - 12 * mm
        if getattr(customer, "address", None):
            for ln in wrap_text(customer.address, LABEL_FONT[0], LABEL_FONT[1], 65 * mm, 2):
                p.drawString(left_x, cur_y, ln)
                cur_y -= 4.5 * mm

        phone = (
            getattr(customer, "phone", None) or
            getattr(customer, "mobile", None) or
            getattr(customer, "contact", None)
        )
        if phone:
            p.setFont("Helvetica", 8.5)
            p.drawString(left_x, cur_y, f"☎ {phone}")

        meta_x = PAGE_WIDTH - RIGHT - 3 * mm
        box_width = 48 * mm
        box_height = 20 * mm

        p.setFillColor(LIGHT_GRAY)
        p.setStrokeColor(BORDER)
        p.setLineWidth(0.5)
        p.roundRect(meta_x - box_width, bill_y - box_height + 2 * mm, box_width, box_height , 2 * mm, stroke=1, fill=1)

        p.setFont("Helvetica-Bold", 8)
        p.setFillColor(MUTED)
        p.drawString(meta_x - box_width + 3 * mm, bill_y - 4 * mm, "Date:")
        p.drawString(meta_x - box_width + 3 * mm, bill_y - 9 * mm, "Invoice No:")

        p.setFont("Helvetica-Bold", 9)
        p.setFillColor(TEXT)
        p.drawRightString(meta_x - 3 * mm, bill_y - 4 * mm, invoice.date.strftime("%d %b %Y"))
        p.drawRightString(meta_x - 3 * mm, bill_y - 9 * mm, f"#{invoice.id}")

        table_y = bill_y - 25 * mm

        amount_x = PAGE_WIDTH - RIGHT - 3 * mm
        discount_x = amount_x - 22 * mm
        unit_x = discount_x - 13 * mm
        qty_x = unit_x - 18 * mm
        desc_x = LEFT + 11 * mm
        sno_x = LEFT + 3 * mm
        desc_w = qty_x - desc_x - 4 * mm

        p.setFillColor(PRIMARY)
        p.roundRect(LEFT + 2 * mm, table_y - 1.5 * mm, PAGE_WIDTH - LEFT - RIGHT - 4 * mm, 7 * mm, 1.5 * mm, stroke=0, fill=1)

        p.setFont(*HEADER_FONT)
        p.setFillColor(Color(1, 1, 1))
        p.drawString(sno_x, table_y + 0.8 * mm, "S.No")
        p.drawString(desc_x, table_y + 0.8 * mm, "Description")
        p.drawRightString(qty_x, table_y + 0.8 * mm, "Qty")
        p.drawRightString(unit_x, table_y + 0.8 * mm, "Unit Price")
        p.drawRightString(discount_x, table_y + 0.8 * mm, "Disc")
        p.drawRightString(amount_x, table_y + 0.8 * mm, "Amount")

        p.setFillColor(TEXT)

        y = table_y - 7 * mm
        row_height = 6 * mm
        bottom_reserve = BOTTOM + 40 * mm
        serial = 1

        def format_item_discount(it):
            d = getattr(it, "discount", None)
            if d is None:
                d = getattr(it, "discount_percent", None)
            if d is not None:
                try:
                    d_dec = Decimal(d).quantize(Decimal("0.01"))
                    if abs(d_dec) <= 100:
                        return f"{format(d_dec, 'f').rstrip('0').rstrip('.')}%"
                except Exception:
                    pass
            amt = getattr(it, "discount_amount", None)
            if amt is None:
                try:
                    if getattr(it, "price_per_item", None) is not None and getattr(it, "quantity", None) is not None:
                        inferred = (Decimal(it.price_per_item) * Decimal(it.quantity) - Decimal(it.total))
                        if inferred and inferred != 0:
                            return money_fmt(inferred)
                except Exception:
                    pass
            if amt is not None:
                return money_fmt(amt)
            return "-"

        for it in items:
            if y < bottom_reserve:
                p.showPage()
                y = draw_header(PAGE_HEIGHT - TOP - 8 * mm)
                table_y = y - 20 * mm

                p.setFillColor(PRIMARY)
                p.roundRect(LEFT + 2 * mm, table_y - 1.5 * mm, PAGE_WIDTH - LEFT - RIGHT - 4 * mm, 7 * mm, 1.5 * mm, stroke=0, fill=1)

                p.setFont(*HEADER_FONT)
                p.setFillColor(Color(1, 1, 1))
                p.drawString(sno_x, table_y + 0.8 * mm, "S.No")
                p.drawString(desc_x, table_y + 0.8 * mm, "Description")
                p.drawRightString(qty_x, table_y + 0.8 * mm, "Qty")
                p.drawRightString(unit_x, table_y + 0.8 * mm, "Unit Price")
                p.drawRightString(discount_x, table_y + 0.8 * mm, "Disc")
                p.drawRightString(amount_x, table_y + 0.8 * mm, "Amount")

                p.setFillColor(TEXT)
                y = table_y - 7 * mm

            if serial % 2 == 0:
                p.setFillColor(Color(0.98, 0.98, 0.98))
                p.rect(LEFT + 2 * mm, y - 1 * mm, PAGE_WIDTH - LEFT - RIGHT - 4 * mm, row_height, stroke=0, fill=1)
                p.setFillColor(TEXT)

            desc = it.custom_name or (it.item.name if it.item else "Deleted Item")
            lines = wrap_text(desc, BODY_FONT[0], BODY_FONT[1], desc_w, 2)

            p.setFont(*BODY_FONT)
            p.setFillColor(MUTED)
            p.drawString(sno_x, y, str(serial))

            p.setFillColor(TEXT)
            if lines:
                p.drawString(desc_x, y, lines[0])
                if len(lines) > 1:
                    p.setFont("Helvetica", 7.5)
                    p.drawString(desc_x, y - 3 * mm, lines[1])
                    p.setFont(*BODY_FONT)

            p.drawRightString(qty_x, y, f"{_to_decimal(it.quantity):,.2f}")
            p.drawRightString(unit_x, y, money_fmt(it.price_per_item))

            p.setFont("Helvetica", 8)
            p.drawRightString(discount_x, y, format_item_discount(it))

            p.setFont(*NUM_FONT)
            p.setFillColor(PRIMARY)
            p.drawRightString(amount_x, y, money_fmt(it.total))

            p.setFillColor(TEXT)
            p.setFont(*BODY_FONT)

            y -= row_height
            serial += 1

        if y < bottom_reserve + 5 * mm:
            p.showPage()
            y = draw_header(PAGE_HEIGHT - TOP - 8 * mm)
            y -= 20 * mm

        y -= 4 * mm
        box_x = PAGE_WIDTH - RIGHT - 60 * mm
        box_width = 60 * mm

        discount = getattr(invoice, "discount", Decimal("0.00"))
        has_discount = discount and discount > 0
        box_height = 42 * mm if has_discount else 37 * mm

        p.setFillColor(LIGHT_GRAY)
        p.setStrokeColor(BORDER)
        p.setLineWidth(0.7)
        p.roundRect(box_x - 2 * mm, y - box_height + 2 * mm, box_width, box_height, 2 * mm, stroke=1, fill=1)

        def total_line(label, value, yy, bold=False, color=None):
            font_size = 10 if bold else 8.5
            p.setFont("Helvetica-Bold" if bold else "Helvetica", font_size)
            p.setFillColor(color or TEXT)
            p.drawString(box_x + 2 * mm, yy, label)
            p.drawRightString(PAGE_WIDTH - RIGHT - 5 * mm, yy, money_fmt(value))

        line_y = y - 4 * mm
        spacing = 5.5 * mm

        total_line("Opening Balance:", opening_balance, line_y)
        line_y -= spacing

        total_line("Subtotal:", invoice.total, line_y)
        line_y -= spacing

        if has_discount:
            p.setFillColor(SUCCESS)
            total_line(f"Discount ({discount}%):", -(invoice.total * discount / 100), line_y, color=SUCCESS)
            line_y -= spacing

        total_line("Shipping:", invoice.shipping, line_y)
        line_y -= spacing + 1.5 * mm

        p.setStrokeColor(PRIMARY)
        p.setLineWidth(1.2)
        p.line(box_x + 2 * mm, line_y + 3 * mm, PAGE_WIDTH - RIGHT - 5 * mm, line_y + 3 * mm)

        p.setFillColor(PRIMARY)
        p.rect(box_x, line_y - 1 * mm, box_width - 4 * mm, 7 * mm, stroke=0, fill=1)
        p.setFont("Helvetica-Bold", 10)
        p.setFillColor(Color(1, 1, 1))
        p.drawString(box_x + 2 * mm, line_y + 0.5 * mm, "Invoice Total:")
        p.drawRightString(PAGE_WIDTH - RIGHT - 5 * mm, line_y + 0.5 * mm, money_fmt(invoice.grand_total))

        line_y -= spacing + 2 * mm
        p.setFillColor(TEXT)

        total_line("Closing Balance:", closing_balance, line_y, bold=True)

        p.setStrokeColor(ACCENT)
        p.setLineWidth(1)
        p.line(LEFT + 30 * mm, BOTTOM + 10 * mm, PAGE_WIDTH - RIGHT - 30 * mm, BOTTOM + 10 * mm)

        p.setFont("Helvetica-Bold", 8.5)
        p.setFillColor(PRIMARY)
        p.drawCentredString(PAGE_WIDTH / 2, BOTTOM + 6 * mm, "Thank you for your business!")

        p.setFont("Helvetica", 7)
        p.setFillColor(MUTED)
        p.drawCentredString(PAGE_WIDTH / 2, BOTTOM + 2 * mm, "This is a computer-generated invoice.")

        p.save()
        return response


InvoiceDetailView = ImprovedInvoiceDetailView


# -------------------- create view --------------------
class InvoiceCreateView(CreateView):
    model = Invoice
    template_name = "invoice/invoicecreate.html"
    form_class = InvoiceForm

    def get(self, request, *args, **kwargs):
        form = self.form_class()
        try:
            if request.user.profile.default_store:
                form.fields['store'].initial = request.user.profile.default_store
        except Exception:
            pass
        items = InvoiceItemFormSet(prefix="items")
        return render(request, self.template_name, {"form": form, "items": items})

    def _push_formset_errors_to_messages(self, request, items_formset):
        for err in items_formset.non_form_errors():
            messages.error(request, f"Items: {err}")
        for idx, f in enumerate(items_formset.forms):
            for err in f.non_field_errors():
                messages.error(request, f"Row {idx + 1}: {err}")
            for field_name, errs in f.errors.items():
                if field_name.startswith("items-") or field_name in (f"{f.prefix}-DELETE",):
                    continue
                for e in errs:
                    messages.error(request, f"Row {idx + 1} - {field_name}: {e}")

    def _disconnect_invoice_signals(self):
        try:
            import invoice.models as invoice_models
            from django.db.models.signals import pre_save
            if hasattr(invoice_models, "on_item_saved_update_totals"):
                post_save.disconnect(receiver=invoice_models.on_item_saved_update_totals, sender=InvoiceItem)
            if hasattr(invoice_models, "on_item_deleted_update_totals"):
                post_delete.disconnect(receiver=invoice_models.on_item_deleted_update_totals, sender=InvoiceItem)
            if hasattr(invoice_models, "invoiceitem_pre_save"):
                pre_save.disconnect(receiver=invoice_models.invoiceitem_pre_save, sender=InvoiceItem)
            if hasattr(invoice_models, "invoiceitem_post_save_adjust_stock"):
                post_save.disconnect(receiver=invoice_models.invoiceitem_post_save_adjust_stock, sender=InvoiceItem)
            if hasattr(invoice_models, "invoiceitem_post_delete_restore_stock"):
                post_delete.disconnect(receiver=invoice_models.invoiceitem_post_delete_restore_stock, sender=InvoiceItem)
        except Exception as e:
            logger.warning("Could not disconnect invoice signals: %s", e)

    def _reconnect_invoice_signals(self):
        try:
            import invoice.models as invoice_models
            from django.db.models.signals import pre_save
            if hasattr(invoice_models, "on_item_saved_update_totals"):
                post_save.connect(receiver=invoice_models.on_item_saved_update_totals, sender=InvoiceItem)
            if hasattr(invoice_models, "on_item_deleted_update_totals"):
                post_delete.connect(receiver=invoice_models.on_item_deleted_update_totals, sender=InvoiceItem)
            if hasattr(invoice_models, "invoiceitem_pre_save"):
                pre_save.connect(receiver=invoice_models.invoiceitem_pre_save, sender=InvoiceItem)
            if hasattr(invoice_models, "invoiceitem_post_save_adjust_stock"):
                post_save.connect(receiver=invoice_models.invoiceitem_post_save_adjust_stock, sender=InvoiceItem)
            if hasattr(invoice_models, "invoiceitem_post_delete_restore_stock"):
                post_delete.connect(receiver=invoice_models.invoiceitem_post_delete_restore_stock, sender=InvoiceItem)
        except Exception as e:
            logger.warning("Could not reconnect invoice signals: %s", e)

    def post(self, request, *args, **kwargs):
        form = self.form_class(request.POST)
        items = InvoiceItemFormSet(request.POST, prefix="items")

        if not form.is_valid():
            for fld, errs in form.errors.items():
                for e in errs:
                    messages.error(request, f"{fld}: {e}")

        if form.is_valid() and items.is_valid():
            invoice = form.save(commit=False)
            new_counts = _build_counts_from_formset(items)
            old_counts = {}
            deltas = {}
            for key, new_qty in new_counts.items():
                old_qty = old_counts.get(key, Decimal("0.00"))
                delta = new_qty - old_qty
                if delta != Decimal("0.00"):
                    deltas[key] = delta

            insufficient = []
            for (item_id,), delta in deltas.items():
                if delta > 0:
                    if item_id is None:
                        continue
                    try:
                        item_obj = Item.objects.get(pk=item_id)
                        available = _to_decimal(item_obj.stock)
                    except Item.DoesNotExist:
                        available = Decimal("0.00")
                    if delta > available:
                        insufficient.append((item_id, delta, available))

            if insufficient:
                for item_id, need, have in insufficient:
                    item_obj = Item.objects.filter(pk=item_id).first()
                    name = item_obj.name if item_obj else f"Item #{item_id}"
                    messages.error(request, f"Not enough stock for {name}: need {need}, available {have}.")
                messages.error(request, "Invoice not saved due to insufficient stock.")
                return render(request, self.template_name, {"form": form, "items": items})

            with transaction.atomic():
                invoice.save()
                self._disconnect_invoice_signals()

                to_save_instances = items.save(commit=False)
                to_delete = getattr(items, "deleted_objects", None) or []

                for obj in to_delete:
                    if obj.item_id:
                        try:
                            it = Item.objects.select_for_update().get(pk=obj.item_id)
                            try:
                                add_qty = int(_to_decimal(obj.quantity).quantize(0, rounding=ROUND_HALF_UP))
                            except Exception:
                                add_qty = int(_to_decimal(obj.quantity))

                            store = getattr(invoice, 'store', None)
                            if store:
                                from locations.models import StoreStock
                                StoreStock.adjust(store, it, +add_qty)
                                it.stock = StoreStock.global_total(it)
                                it.save(update_fields=["stock"])
                            else:
                                it.stock = int(_to_decimal(it.stock) + add_qty)
                                it.save(update_fields=["stock"])
                        except Item.DoesNotExist:
                            pass
                    obj.delete()

                for (item_id,), delta in deltas.items():
                    if delta <= 0:
                        continue
                    if item_id is None:
                        continue
                    try:
                        item_obj = Item.objects.select_for_update().get(pk=item_id)
                        try:
                            int_delta = int(delta.quantize(0, rounding=ROUND_HALF_UP))
                        except Exception:
                            int_delta = int(delta)

                        store = getattr(invoice, 'store', None)
                        if store:
                            from locations.models import StoreStock
                            StoreStock.adjust(store, item_obj, -int_delta)
                            item_obj.stock = StoreStock.global_total(item_obj)
                            item_obj.save(update_fields=["stock"])
                        else:
                            item_obj.stock = int(_to_decimal(item_obj.stock) - int_delta)
                            if item_obj.stock < 0:
                                item_obj.stock = 0
                            item_obj.save(update_fields=["stock"])
                    except Item.DoesNotExist:
                        logger.warning("Item not found during stock adjustment: item_id=%s", item_id)
                        messages.warning(request, f"Note: Could not adjust stock for item {item_id} - not found in inventory.")

                for inst in to_save_instances:
                    inst.invoice = invoice
                    inst.save()

                try:
                    items.save_m2m()
                except Exception:
                    pass

                invoice.total = sum(i.total for i in invoice.items.all())
                invoice.grand_total = invoice.total + invoice.shipping
                invoice.save()
                try:
                    if invoice.customer_id:
                        invoice.customer.update_balance()
                except Exception:
                    pass

                self._reconnect_invoice_signals()

                messages.success(request, "Invoice created successfully.")
                return redirect(self.get_success_url())

        if not items.is_valid():
            self._push_formset_errors_to_messages(request, items)

        messages.error(request, "Invoice not saved - please fix the errors and try again.")
        return render(request, self.template_name, {"form": form, "items": items})

    def get_success_url(self):
        return reverse("invoicelist")


# -------------------- update view --------------------
class InvoiceUpdateView(UpdateView):
    model = Invoice
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"
    template_name = "invoice/invoiceupdate.html"
    form_class = InvoiceForm

    def get_object(self, queryset=None):
        uuid = self.kwargs.get("uuid")
        return get_object_or_404(Invoice, uuid=uuid)

    def _format_decimal_for_display(self, value):
        if value is None:
            return ""
        try:
            d = _to_decimal(value) if "_to_decimal" in globals() else Decimal(value)
        except Exception:
            try:
                d = Decimal(str(value))
            except Exception:
                return str(value)
        d_q = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return format(d_q, "f").rstrip("0").rstrip(".")

    def _normalize_decimal_for_storage(self, value):
        if value is None or value == "":
            return Decimal("0.00")
        try:
            d = _to_decimal(value) if "_to_decimal" in globals() else Decimal(value)
        except Exception:
            try:
                d = Decimal(str(value))
            except Exception:
                return Decimal("0.00")
        return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.form_class(instance=self.object)
        items = InvoiceItemFormSet(instance=self.object, prefix="items")

        for f in items.forms:
            if "discount" in getattr(f, "fields", {}):
                raw = f.initial.get("discount", None)
                if raw is None and hasattr(f, "instance"):
                    raw = getattr(f.instance, "discount", None)
                f.initial["discount"] = self._format_decimal_for_display(raw)

        return render(request, self.template_name, {"form": form, "items": items})

    def _push_formset_errors_to_messages(self, request, items_formset):
        for err in items_formset.non_form_errors():
            messages.error(request, f"Items: {err}")
        for idx, f in enumerate(items_formset.forms):
            for err in f.non_field_errors():
                messages.error(request, f"Row {idx + 1}: {err}")
            for field_name, errs in f.errors.items():
                if field_name.startswith("items-") or field_name in (f"{f.prefix}-DELETE",):
                    continue
                for e in errs:
                    messages.error(request, f"Row {idx + 1} - {field_name}: {e}")

    def _disconnect_invoice_signals(self):
        try:
            import invoice.models as invoice_models
            from django.db.models.signals import pre_save
            if hasattr(invoice_models, "on_item_saved_update_totals"):
                post_save.disconnect(receiver=invoice_models.on_item_saved_update_totals, sender=InvoiceItem)
            if hasattr(invoice_models, "on_item_deleted_update_totals"):
                post_delete.disconnect(receiver=invoice_models.on_item_deleted_update_totals, sender=InvoiceItem)
            if hasattr(invoice_models, "invoiceitem_pre_save"):
                pre_save.disconnect(receiver=invoice_models.invoiceitem_pre_save, sender=InvoiceItem)
            if hasattr(invoice_models, "invoiceitem_post_save_adjust_stock"):
                post_save.disconnect(receiver=invoice_models.invoiceitem_post_save_adjust_stock, sender=InvoiceItem)
            if hasattr(invoice_models, "invoiceitem_post_delete_restore_stock"):
                post_delete.disconnect(receiver=invoice_models.invoiceitem_post_delete_restore_stock, sender=InvoiceItem)
        except Exception as e:
            logger.warning("Could not disconnect invoice signals: %s", e)

    def _reconnect_invoice_signals(self):
        try:
            import invoice.models as invoice_models
            from django.db.models.signals import pre_save
            if hasattr(invoice_models, "on_item_saved_update_totals"):
                post_save.connect(receiver=invoice_models.on_item_saved_update_totals, sender=InvoiceItem)
            if hasattr(invoice_models, "on_item_deleted_update_totals"):
                post_delete.connect(receiver=invoice_models.on_item_deleted_update_totals, sender=InvoiceItem)
            if hasattr(invoice_models, "invoiceitem_pre_save"):
                pre_save.connect(receiver=invoice_models.invoiceitem_pre_save, sender=InvoiceItem)
            if hasattr(invoice_models, "invoiceitem_post_save_adjust_stock"):
                post_save.connect(receiver=invoice_models.invoiceitem_post_save_adjust_stock, sender=InvoiceItem)
            if hasattr(invoice_models, "invoiceitem_post_delete_restore_stock"):
                post_delete.connect(receiver=invoice_models.invoiceitem_post_delete_restore_stock, sender=InvoiceItem)
        except Exception as e:
            logger.warning("Could not reconnect invoice signals: %s", e)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.form_class(request.POST, instance=self.object)
        items = InvoiceItemFormSet(request.POST, instance=self.object, prefix="items")

        if not form.is_valid():
            for fld, errs in form.errors.items():
                for e in errs:
                    messages.error(request, f"{fld}: {e}")

        if form.is_valid() and items.is_valid():
            invoice = form.save(commit=False)

            old_qs = InvoiceItem.objects.filter(invoice=invoice)
            old_counts = _build_counts_from_queryset(old_qs)
            new_counts = _build_counts_from_formset(items)

            deltas = {}
            all_keys = set(old_counts.keys()) | set(new_counts.keys())
            for key in all_keys:
                new_q = new_counts.get(key, Decimal("0.00"))
                old_q = old_counts.get(key, Decimal("0.00"))
                delta = new_q - old_q
                if delta != Decimal("0.00"):
                    deltas[key] = delta

            insufficient = []
            for (item_id,), delta in deltas.items():
                if delta > 0:
                    if item_id is None:
                        continue
                    try:
                        item_obj = Item.objects.get(pk=item_id)
                        available = _to_decimal(item_obj.stock)
                    except Item.DoesNotExist:
                        available = Decimal("0.00")
                    if delta > available:
                        insufficient.append((item_id, delta, available))

            if insufficient:
                for item_id, need, have in insufficient:
                    item_obj = Item.objects.filter(pk=item_id).first()
                    name = item_obj.name if item_obj else f"Item #{item_id}"
                    messages.error(request, f"Not enough stock for {name}: need {need}, available {have}.")
                messages.error(request, "Invoice not saved due to insufficient stock.")
                for f in items.forms:
                    if "discount" in getattr(f, "fields", {}):
                        raw = f.initial.get("discount", None)
                        if raw is None and hasattr(f, "instance"):
                            raw = getattr(f.instance, "discount", None)
                        f.initial["discount"] = self._format_decimal_for_display(raw)
                return render(request, self.template_name, {"form": form, "items": items})

            with transaction.atomic():
                invoice.save()
                self._disconnect_invoice_signals()

                to_save_instances = items.save(commit=False)
                to_delete = getattr(items, "deleted_objects", None) or []

                for obj in to_delete:
                    if obj.item_id:
                        try:
                            it = Item.objects.select_for_update().get(pk=obj.item_id)
                            try:
                                add_qty = int(_to_decimal(obj.quantity).quantize(0, rounding=ROUND_HALF_UP))
                            except Exception:
                                add_qty = int(_to_decimal(obj.quantity))

                            store = getattr(invoice, 'store', None)
                            if store:
                                from locations.models import StoreStock
                                StoreStock.adjust(store, it, +add_qty)
                                it.stock = StoreStock.global_total(it)
                                it.save(update_fields=["stock"])
                            else:
                                it.stock = int(_to_decimal(it.stock) + add_qty)
                                it.save(update_fields=["stock"])
                        except Item.DoesNotExist:
                            pass
                    obj.delete()

                for (item_id,), delta in deltas.items():
                    if delta > 0:
                        if item_id is None:
                            continue
                        try:
                            item_obj = Item.objects.select_for_update().get(pk=item_id)
                            try:
                                int_delta = int(delta.quantize(0, rounding=ROUND_HALF_UP))
                            except Exception:
                                int_delta = int(delta)

                            store = getattr(invoice, 'store', None)
                            if store:
                                from locations.models import StoreStock
                                StoreStock.adjust(store, item_obj, -int_delta)
                                item_obj.stock = StoreStock.global_total(item_obj)
                                item_obj.save(update_fields=["stock"])
                            else:
                                item_obj.stock = int(_to_decimal(item_obj.stock) - int_delta)
                                if item_obj.stock < 0:
                                    item_obj.stock = 0
                                item_obj.save(update_fields=["stock"])
                        except Item.DoesNotExist:
                            logger.warning("Item not found during stock adjustment: item_id=%s", item_id)
                            messages.warning(request, f"Note: Could not adjust stock for item {item_id} - not found in inventory.")

                for inst in to_save_instances:
                    inst.invoice = invoice
                    try:
                        inst.discount = self._normalize_decimal_for_storage(getattr(inst, "discount", None))
                    except Exception:
                        try:
                            inst.discount = Decimal(str(getattr(inst, "discount", "0")))
                        except Exception:
                            inst.discount = Decimal("0.00")
                    inst.save()

                try:
                    items.save_m2m()
                except Exception:
                    pass

                invoice.total = sum(i.total for i in invoice.items.all())
                invoice.grand_total = invoice.total + invoice.shipping
                invoice.save()
                try:
                    if invoice.customer_id:
                        invoice.customer.update_balance()
                except Exception:
                    pass

                self._reconnect_invoice_signals()

                messages.success(request, "Invoice updated successfully.")
                return redirect(self.get_success_url())

        if not items.is_valid():
            self._push_formset_errors_to_messages(request, items)

        for f in items.forms:
            if "discount" in getattr(f, "fields", {}):
                raw = None
                try:
                    raw = f.data.get(f.add_prefix("discount"))
                except Exception:
                    pass
                if raw in (None, ""):
                    raw = f.initial.get("discount", None)
                    if raw is None and hasattr(f, "instance"):
                        raw = getattr(f.instance, "discount", None)
                f.initial["discount"] = self._format_decimal_for_display(raw)

        messages.error(request, "Invoice not saved - please fix the errors and try again.")
        return render(request, self.template_name, {"form": form, "items": items})

    def get_success_url(self):
        return reverse("invoicelist")


# -------------------- delete view --------------------
class InvoiceDeleteView(DeleteView):
    model = Invoice
    template_name = "invoice/invoicedelete.html"

    def get_object(self, queryset=None):
        return get_object_or_404(Invoice, uuid=self.kwargs["uuid"])

    def get_success_url(self):
        return reverse("invoicelist")
