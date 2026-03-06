# invoice/views.py
# Deterministic stock adjustments in views (prevents double-decrement).
# Validates availability and provides clear messages for users.

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import logging
import os

from django.urls import reverse
from django.shortcuts import redirect, render, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import DetailView, CreateView, UpdateView, DeleteView
from django_tables2 import SingleTableView
from django_tables2.export.views import ExportMixin

from django.db.models import Sum
from django.views.decorators.http import require_GET
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models.signals import post_save, post_delete

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import black, HexColor
from django.conf import settings

from .models import Invoice, InvoiceItem
from .tables import InvoiceTable
from .forms import InvoiceForm, InvoiceItemFormSet

from store.models import Item

logger = logging.getLogger(__name__)


# --- Helpers ----------------------------------------------------------------
def _to_decimal(value):
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


def _build_counts_from_queryset(qs):
    """
    Given an iterable of InvoiceItem-like objects (with attributes item_id, quantity),
    return a dict keyed by (item_id,) -> Decimal(total_quantity).
    item_id may be None for custom items.
    """
    counts = {}
    for r in qs:
        key = (getattr(r, "item_id", None),)
        qty = _to_decimal(getattr(r, "quantity", 0))
        counts[key] = counts.get(key, Decimal("0.00")) + qty
    return counts


def _build_counts_from_formset(formset):
    """
    Build counts by reading formset.cleaned_data for each form (skip deleted forms).
    """
    counts = {}
    for f in formset.forms:
        if not hasattr(f, "cleaned_data"):
            continue
        cd = f.cleaned_data
        # if formset marks deletion
        if cd.get("DELETE"):
            continue
        item = cd.get("item")  # may be None for custom product
        qty = _to_decimal(cd.get("quantity", 0))
        key = (item.pk if item else None,)
        counts[key] = counts.get(key, Decimal("0.00")) + qty
    return counts


# --- API endpoints ----------------------------------------------------------
@require_GET
def api_item_colors(request, pk):
    """
    Formerly returned per-color variant stock. Since invoices no longer use colors,
    return a single 'default' entry with the current Item.stock.

    Response:
      [
        {"id": null, "name": "Default", "stock": 12},
      ]
    """
    try:
        item = Item.objects.get(pk=pk)
    except ObjectDoesNotExist:
        return JsonResponse({"error": "Item not found"}, status=404)

    stock = int(item.stock or 0)
    data = [{"id": None, "name": "Default", "stock": stock}]
    return JsonResponse(data, safe=False)


@require_GET
def api_item_price(request, pk):
    """Return {"price": "123.45"} formatted as string."""
    try:
        item = Item.objects.get(pk=pk)
    except ObjectDoesNotExist:
        return JsonResponse({"error": "Item not found"}, status=404)
    price = Decimal(item.price or 0).quantize(Decimal("0.01"))
    return JsonResponse({"price": f"{price:.2f}"})


# --- Invoice list / PDF detail ---------------------------------------------
class InvoiceListView(LoginRequiredMixin, ExportMixin, SingleTableView):
    model = Invoice
    table_class = InvoiceTable
    template_name = "invoice/invoicelist.html"
    context_object_name = "invoices"
    paginate_by = 10
    table_pagination = False


class InvoiceDetailView(DetailView):
    model = Invoice

    def get(self, request, *args, **kwargs):
        invoice = self.get_object()
        customer = invoice.customer
        items = invoice.items.all()

        # NOTE: use date__lt for earlier invoices but include payments on the same date
        prev_invoices_total = (
            customer.invoices.filter(date__lt=invoice.date).aggregate(total=Sum("grand_total")).get("total") or Decimal("0.00")
        )
        # include payments on the same date (<=) so same-day payments affect opening balance
        prev_payments_total = (
            customer.payments.filter(date__lte=invoice.date).aggregate(total=Sum("amount")).get("total") or Decimal("0.00")
        )
        opening_balance = (Decimal(prev_invoices_total) - Decimal(prev_payments_total)).quantize(Decimal("0.01"))
        closing_balance = (opening_balance + Decimal(invoice.grand_total)).quantize(Decimal("0.01"))

        # PDF generation (ReportLab)
        response = HttpResponse(content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="Invoice_{invoice.slug}.pdf"'

        # === START: PDF layout and drawing ===
        width, height = A4
        p = canvas.Canvas(response, pagesize=A4)

        LOGO_PATH = os.path.join(settings.BASE_DIR, "static", "images", "lenter_logo.png")
        SHOP_NAME = "AL MADINA ENTERPRISE"
        SHOP_META = "Karachi, Pakistan | +92 335 0040521"
        PRIMARY = HexColor("#0e4b66")
        TEXT = black

        def money_fmt(val):
            """Return a string with thousands separators and 2 decimals."""
            try:
                v = Decimal(val)
                return f"{v:,.2f}"
            except Exception:
                try:
                    return f"{float(val):,.2f}"
                except Exception:
                    return "0.00"

        def draw_header():
            # Draw logo left (if exists), shop name/meta on the right of logo, and centered title
            try:
                if os.path.exists(LOGO_PATH):
                    logo = ImageReader(LOGO_PATH)
                    # scale logo to a reasonable size
                    logo_w = 35 * mm
                    # draw at the top-left
                    p.drawImage(logo, 20 * mm, height - (28 * mm), width=logo_w, preserveAspectRatio=True, mask="auto")
                    text_x = 20 * mm + logo_w + (6 * mm)
                else:
                    text_x = 20 * mm
            except Exception as e:
                logger.debug("Failed to draw logo: %s", e)
                text_x = 20 * mm

            p.setFont("Helvetica-Bold", 16)
            p.setFillColor(PRIMARY)
            p.drawString(text_x, height - (22 * mm), SHOP_NAME)

            p.setFont("Helvetica", 9)
            p.setFillColor(TEXT)
            p.drawString(text_x, height - (28 * mm), SHOP_META)

            # centered invoice title
            p.setFont("Helvetica-Bold", 14)
            p.drawCentredString(width / 2, height - (40 * mm), "INVOICE")

        # initial header
        draw_header()

        # Bill To block (left), meta block (right)
        p.setFont("Helvetica", 11)
        bill_x = 30 * mm
        bill_y = height - (52 * mm)

        p.setFont("Helvetica-Bold", 11)
        p.drawString(bill_x, bill_y, "Bill To:")
        p.setFont("Helvetica-Bold", 10)
        try:
            # prefer get_full_name if available
            full_name = customer.get_full_name() if hasattr(customer, "get_full_name") else getattr(customer, "name", str(customer))
        except Exception:
            full_name = str(customer)
        p.drawString(bill_x, bill_y - 6 * mm, full_name)

        p.setFont("Helvetica", 9)
        line_y = bill_y - 12 * mm
        if getattr(customer, "address", None):
            p.drawString(bill_x, line_y, str(customer.address))
            line_y -= 6 * mm

        # safe phone detection: try common attribute names
        phone = (
            getattr(customer, "phone", None)
            or getattr(customer, "mobile", None)
            or getattr(customer, "contact", None)
            or getattr(customer, "phone_number", None)
        )
        if phone:
            p.drawString(bill_x, line_y, f"Phone: {phone}")
            line_y -= 6 * mm

        # right-side metadata (date / invoice no)
        p.setFont("Helvetica", 9)
        p.drawRightString(width - 30 * mm, bill_y, f"Date: {invoice.date.strftime('%Y-%m-%d')}")
        p.drawRightString(width - 30 * mm, bill_y - 6 * mm, f"Invoice No: {invoice.id}")

        # Table header starting Y
        y = height - (92 * mm)
        x = {
            "sno": 25 * mm,
            "desc": 45 * mm,
            "qty": 115 * mm,
            "unit_price": 140 * mm,
            "discount": 162 * mm,
            "amount": width - 20 * mm,
        }

        p.setFont("Helvetica-Bold", 11)
        p.drawString(x["sno"], y, "S.No")
        p.drawString(x["desc"], y, "Description")
        p.drawRightString(x["qty"], y, "Qty")
        p.drawRightString(x["unit_price"], y, "Unit(s)")
        p.drawRightString(x["discount"], y, "Disc %")
        p.drawRightString(x["amount"], y, "Amount (Rs)")

        y -= 10 * mm
        p.line(20 * mm, y, width - 20 * mm, y)
        y -= 6 * mm

        # table rows
        p.setFont("Helvetica", 10)
        serial = 1
        row_h = 7 * mm
        bottom_margin = 25 * mm

        for inv_item in items:
            # page break
            if y < bottom_margin:
                p.showPage()
                draw_header()
                y = height - (92 * mm)
                p.setFont("Helvetica-Bold", 11)
                p.drawString(x["sno"], y, "S.No")
                p.drawString(x["desc"], y, "Description")
                p.drawRightString(x["qty"], y, "Qty")
                p.drawRightString(x["unit_price"], y, "Unit(s)")
                p.drawRightString(x["discount"], y, "Disc %")
                p.drawRightString(x["amount"], y, "Amount (Rs)")
                y -= 10 * mm
                p.line(20 * mm, y, width - 20 * mm, y)
                y -= 6 * mm
                p.setFont("Helvetica", 10)

            product_name = inv_item.custom_name or (inv_item.item.name if inv_item.item else "Deleted Item")
            # protect extremely long names
            short_desc = product_name if len(product_name) <= 100 else product_name[:97] + "..."

            p.drawString(x["sno"], y, str(serial))
            p.drawString(x["desc"], y, short_desc)
            p.drawRightString(x["qty"], y, str(inv_item.quantity))

            # unit price
            try:
                p.drawRightString(x["unit_price"], y, money_fmt(inv_item.price_per_item))
            except Exception:
                p.drawRightString(x["unit_price"], y, str(inv_item.price_per_item))

            # discount
            try:
                disc_val = getattr(inv_item, "discount", 0)
                p.drawRightString(x["discount"], y, money_fmt(disc_val))
            except Exception:
                p.drawRightString(x["discount"], y, "0.00")

            # amount
            try:
                p.drawRightString(x["amount"], y, money_fmt(inv_item.total))
            except Exception:
                p.drawRightString(x["amount"], y, str(inv_item.total))

            p.line(20 * mm, y - (1 * mm), width - 20 * mm, y - (1 * mm))
            y -= row_h
            serial += 1

        # ensure space for totals
        if y < bottom_margin + (30 * mm):
            p.showPage()
            draw_header()
            y = height - (92 * mm)

        y -= 6 * mm
        p.setFont("Helvetica", 10)
        p.drawRightString(width - 60 * mm, y, "Opening Balance:")
        p.drawRightString(width - 30 * mm, y, money_fmt(opening_balance))

        y -= 6 * mm
        p.drawRightString(width - 60 * mm, y, "Subtotal:")
        p.drawRightString(width - 30 * mm, y, money_fmt(invoice.total))

        y -= 6 * mm
        p.drawRightString(width - 60 * mm, y, "Shipping:")
        p.drawRightString(width - 30 * mm, y, money_fmt(invoice.shipping))

        y -= 8 * mm
        p.setFont("Helvetica-Bold", 12)
        p.drawRightString(width - 60 * mm, y, "Invoice Total:")
        p.drawRightString(width - 30 * mm, y, money_fmt(invoice.grand_total))

        y -= 8 * mm
        p.setFont("Helvetica", 10)
        p.drawRightString(width - 60 * mm, y, "Closing Balance:")
        p.drawRightString(width - 30 * mm, y, money_fmt(closing_balance))

        # footer
        y -= 16 * mm
        p.setFont("Helvetica", 9)
        p.drawCentredString(width / 2, 20 * mm, "Thank you for your business. This is a computer generated invoice.")

        p.showPage()
        p.save()
        return response
        # === END: PDF layout and drawing ===


# ------------------------- Create invoice ----------------------------------
class InvoiceCreateView(LoginRequiredMixin, CreateView):
    model = Invoice
    template_name = "invoice/invoicecreate.html"
    form_class = InvoiceForm

    def get(self, request, *args, **kwargs):
        form = self.form_class()
        items = InvoiceItemFormSet(prefix="items")
        return render(request, self.template_name, {"form": form, "items": items})

    def _push_formset_errors_to_messages(self, request, items_formset):
        # top-level errors
        for err in items_formset.non_form_errors():
            messages.error(request, f"Items: {err}")

        # per-form errors
        for idx, f in enumerate(items_formset.forms):
            for err in f.non_field_errors():
                messages.error(request, f"Row {idx + 1}: {err}")
            for field_name, errs in f.errors.items():
                # skip management fields
                if field_name.startswith("items-") or field_name in (f"{f.prefix}-DELETE",):
                    continue
                for e in errs:
                    messages.error(request, f"Row {idx + 1} - {field_name}: {e}")

    def _disconnect_invoice_signals(self):
        """
        If your invoice.models registered on_item_saved/on_item_deleted signal handlers,
        disconnect them temporarily to avoid duplicate stock adjustments.
        """
        try:
            import invoice.models as invoice_models
            if hasattr(invoice_models, "on_item_saved"):
                post_save.disconnect(receiver=invoice_models.on_item_saved, sender=InvoiceItem)
            if hasattr(invoice_models, "on_item_deleted"):
                post_delete.disconnect(receiver=invoice_models.on_item_deleted, sender=InvoiceItem)
        except Exception as e:
            logger.debug("Could not disconnect invoice signals: %s", e)

    def _reconnect_invoice_signals(self):
        try:
            import invoice.models as invoice_models
            if hasattr(invoice_models, "on_item_saved"):
                post_save.connect(receiver=invoice_models.on_item_saved, sender=InvoiceItem)
            if hasattr(invoice_models, "on_item_deleted"):
                post_delete.connect(receiver=invoice_models.on_item_deleted, sender=InvoiceItem)
        except Exception as e:
            logger.debug("Could not reconnect invoice signals: %s", e)

    def post(self, request, *args, **kwargs):
        form = self.form_class(request.POST)
        items = InvoiceItemFormSet(request.POST, prefix="items")

        # show form errors
        if not form.is_valid():
            for fld, errs in form.errors.items():
                for e in errs:
                    messages.error(request, f"{fld}: {e}")

        if form.is_valid() and items.is_valid():
            # Pre-validate stock: compute old_counts (empty for create) and new_counts from formset
            invoice = form.save(commit=False)

            # Build counts for requested state (keyed by (item_id,))
            new_counts = _build_counts_from_formset(items)

            # For create, old_counts empty
            old_counts = {}

            # Compute deltas: for each (item_id,) -> delta = new - old
            deltas = {}
            for key, new_qty in new_counts.items():
                old_qty = old_counts.get(key, Decimal("0.00"))
                delta = new_qty - old_qty
                if delta != Decimal("0.00"):
                    deltas[key] = delta

            # Validate availability for positive deltas
            insufficient = []
            for (item_id,), delta in deltas.items():
                if delta > 0:
                    # Skip validation for custom products (item_id is None)
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
                # Build clear messages
                for item_id, need, have in insufficient:
                    item_obj = Item.objects.filter(pk=item_id).first()
                    name = item_obj.name if item_obj else f"Item #{item_id}"
                    messages.error(request, f"Not enough stock for {name}: need {need}, available {have}.")
                messages.error(request, "Invoice not saved due to insufficient stock.")
                return render(request, self.template_name, {"form": form, "items": items})

            # All validation passed: perform save & adjust stock atomically
            with transaction.atomic():
                # Save invoice to get PK
                invoice.save()

                # Disconnect any model-level invoice signals (avoid double-processing)
                self._disconnect_invoice_signals()

                # Save or delete formset items and apply stock deltas
                # Important: call save(commit=False) first so formset.deleted_objects is populated.
                to_save_instances = items.save(commit=False)
                to_delete = getattr(items, "deleted_objects", None) or []

                # perform deletes first (if any), restoring stock where necessary
                for obj in to_delete:
                    if obj.item_id:
                        try:
                            it = Item.objects.select_for_update().get(pk=obj.item_id)
                            try:
                                add_qty = int(_to_decimal(obj.quantity).quantize(0, rounding=ROUND_HALF_UP))
                            except Exception:
                                add_qty = int(_to_decimal(obj.quantity))
                            it.stock = int(_to_decimal(it.stock) + add_qty)
                            it.save(update_fields=["stock"])
                        except Item.DoesNotExist:
                            # nothing to restore
                            pass
                    obj.delete()

                # Apply aggregated deltas (subtract positive deltas)
                for (item_id,), delta in deltas.items():
                    if delta <= 0:
                        continue

                    # Skip stock adjustment for custom products
                    if item_id is None:
                        continue

                    try:
                        item_obj = Item.objects.select_for_update().get(pk=item_id)
                        # convert delta to integer change with rounding
                        try:
                            int_delta = int(delta.quantize(0, rounding=ROUND_HALF_UP))
                        except Exception:
                            int_delta = int(delta)
                        item_obj.stock = int(_to_decimal(item_obj.stock) - int_delta)
                        if item_obj.stock < 0:
                            # clamp to 0 and log
                            logger.warning("Attempt would set negative stock for item %s. Clamping to 0. (was %s, delta %s)", item_obj.pk, item_obj.stock + int_delta, int_delta)
                            item_obj.stock = 0
                        item_obj.save(update_fields=["stock"])
                    except Item.DoesNotExist:
                        logger.warning("Item not found during stock adjustment: item_id=%s", item_id)
                        messages.warning(request, f"Note: Could not adjust stock for item {item_id} - not found in inventory.")

                # Save instances (they become permanent invoice items)
                for inst in to_save_instances:
                    inst.invoice = invoice
                    inst.save()

                # finalize formset m2m if any (unlikely for these models)
                try:
                    items.save_m2m()
                except Exception:
                    pass

                # Recompute totals and update customer balance
                invoice.total = sum(i.total for i in invoice.items.all())
                invoice.grand_total = invoice.total + invoice.shipping
                invoice.save()
                try:
                    if invoice.customer_id:
                        invoice.customer.update_balance()
                except Exception:
                    pass

                # Reconnect signals
                self._reconnect_invoice_signals()

                messages.success(request, "Invoice created successfully.")
                return redirect(self.get_success_url())

        # invalid branch
        if not items.is_valid():
            self._push_formset_errors_to_messages(request, items)

        messages.error(request, "Invoice not saved - please fix the errors and try again.")
        return render(request, self.template_name, {"form": form, "items": items})

    def get_success_url(self):
        return reverse("invoicelist")


# ------------------------- Update invoice ----------------------------------
class InvoiceUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Invoice
    template_name = "invoice/invoiceupdate.html"
    form_class = InvoiceForm

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.form_class(instance=self.object)
        items = InvoiceItemFormSet(instance=self.object, prefix="items")
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
            if hasattr(invoice_models, "on_item_saved"):
                post_save.disconnect(receiver=invoice_models.on_item_saved, sender=InvoiceItem)
            if hasattr(invoice_models, "on_item_deleted"):
                post_delete.disconnect(receiver=invoice_models.on_item_deleted, sender=InvoiceItem)
        except Exception as e:
            logger.debug("Could not disconnect invoice signals: %s", e)

    def _reconnect_invoice_signals(self):
        try:
            import invoice.models as invoice_models
            if hasattr(invoice_models, "on_item_saved"):
                post_save.connect(receiver=invoice_models.on_item_saved, sender=InvoiceItem)
            if hasattr(invoice_models, "on_item_deleted"):
                post_delete.connect(receiver=invoice_models.on_item_deleted, sender=InvoiceItem)
        except Exception as e:
            logger.debug("Could not reconnect invoice signals: %s", e)

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

            # old state counts (keyed by (item_id,))
            old_qs = InvoiceItem.objects.filter(invoice=invoice)
            old_counts = _build_counts_from_queryset(old_qs)

            # requested new state counts
            new_counts = _build_counts_from_formset(items)

            # compute deltas = new - old (positive means we must further decrement stock)
            deltas = {}
            all_keys = set(old_counts.keys()) | set(new_counts.keys())
            for key in all_keys:
                new_q = new_counts.get(key, Decimal("0.00"))
                old_q = old_counts.get(key, Decimal("0.00"))
                delta = new_q - old_q
                if delta != Decimal("0.00"):
                    deltas[key] = delta

            # Validate availability for positive deltas
            insufficient = []
            for (item_id,), delta in deltas.items():
                if delta > 0:
                    # Skip validation for custom products (item_id is None)
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

            # Save atomically and apply deltas
            with transaction.atomic():
                # Save invoice
                invoice.save()

                # disconnect model-level handlers to prevent double adjustments
                self._disconnect_invoice_signals()

                # IMPORTANT: call save(commit=False) first so formset.deleted_objects is populated
                to_save_instances = items.save(commit=False)
                to_delete = getattr(items, "deleted_objects", None) or []

                # Process deletions first (restore stock)
                for obj in to_delete:
                    if obj.item_id:
                        try:
                            it = Item.objects.select_for_update().get(pk=obj.item_id)
                            try:
                                add_qty = int(_to_decimal(obj.quantity).quantize(0, rounding=ROUND_HALF_UP))
                            except Exception:
                                add_qty = int(_to_decimal(obj.quantity))
                            it.stock = int(_to_decimal(it.stock) + add_qty)
                            it.save(update_fields=["stock"])
                        except Item.DoesNotExist:
                            pass
                    obj.delete()

                # Apply positive deltas: subtract from items
                for (item_id,), delta in deltas.items():
                    if delta > 0:
                        # Skip stock adjustment for custom products
                        if item_id is None:
                            continue

                        try:
                            item_obj = Item.objects.select_for_update().get(pk=item_id)
                            try:
                                int_delta = int(delta.quantize(0, rounding=ROUND_HALF_UP))
                            except Exception:
                                int_delta = int(delta)
                            item_obj.stock = int(_to_decimal(item_obj.stock) - int_delta)
                            if item_obj.stock < 0:
                                logger.warning("Attempt would set negative stock for item %s. Clamping to 0. (was %s, delta %s)", item_obj.pk, item_obj.stock + int_delta, int_delta)
                                item_obj.stock = 0
                            item_obj.save(update_fields=["stock"])
                        except Item.DoesNotExist:
                            logger.warning(f"Item not found during update: item_id={item_id}")
                            messages.warning(request, f"Note: Could not adjust stock for item {item_id} - not found in inventory.")

                # Save the (new/updated) form instances
                for inst in to_save_instances:
                    inst.invoice = invoice
                    inst.save()

                try:
                    items.save_m2m()
                except Exception:
                    pass

                # Totals and customer balance
                invoice.total = sum(i.total for i in invoice.items.all())
                invoice.grand_total = invoice.total + invoice.shipping
                invoice.save()
                try:
                    if invoice.customer_id:
                        invoice.customer.update_balance()
                except Exception:
                    pass

                # reconnect signals
                self._reconnect_invoice_signals()

                messages.success(request, "Invoice updated successfully.")
                return redirect(self.get_success_url())

        # invalid
        if not items.is_valid():
            self._push_formset_errors_to_messages(request, items)

        messages.error(request, "Invoice not saved - please fix the errors and try again.")
        return render(request, self.template_name, {"form": form, "items": items})

    def get_success_url(self):
        return reverse("invoicelist")

    def test_func(self):
        return True


# ------------------------- Delete invoice ----------------------------------
class InvoiceDeleteView(LoginRequiredMixin, DeleteView):
    model = Invoice
    template_name = "invoice/invoicedelete.html"

    def get_success_url(self):
        return reverse("invoicelist")
