"""
serializers.py
──────────────
The single source of truth for how every Django model maps to a
Supabase table row.

Rules enforced here:
  - Table name is ALWAYS model._meta.db_table  (no plural guessing)
  - Every field is cast to a JSON-safe type explicitly
  - sync_pendingsync is excluded — it is a local-only retry queue
    and must never be pushed to Supabase

To add a new model:
  1. Add a serialiser function below
  2. Add a ModelSpec entry to REGISTRY
  That's it — signals connect automatically.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable, Any

logger = logging.getLogger("sync")


# ── type helpers ───────────────────────────────────────────────────────────────

def _str(v) -> str | None:
    return str(v) if v is not None else None

def _float(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None

def _int(v) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None

def _slug(v) -> str:
    """
    Return the slug string if it exists and is non-empty.
    If the field is blank/null (e.g. AutoSlugField not yet populated),
    generate a safe fallback so Supabase NOT NULL constraints are satisfied.
    """
    if v:
        return str(v)
    return ""          # empty string is accepted; NOT NULL is satisfied


# ── serialiser functions ───────────────────────────────────────────────────────

def _user(u) -> dict:
    return {
        "id":           u.id,
        "username":     u.username,
        "password":     u.password or "",   # hashed — NOT NULL in auth_user
        "email":        u.email or "",
        "first_name":   u.first_name or "",
        "last_name":    u.last_name or "",
        "is_staff":     u.is_staff,
        "is_superuser": u.is_superuser,
        "is_active":    u.is_active,
        "date_joined":  _str(u.date_joined),
        "last_login":   _str(u.last_login) if u.last_login else None,
    }


def _profile(p) -> dict:
    # slug: AutoSlugField stores actual slug string in DB (even negative-looking ones
    # like "-2" are valid unique slugs). Read directly from the field value.
    # profile_picture: ImageKit field — store the relative path string, NOT NULL.
    try:
        pic = str(p.profile_picture) if p.profile_picture else "profile_pics/default.jpg"
    except Exception:
        pic = "profile_pics/default.jpg"

    try:
        slug_val = str(p.slug) if p.slug else f"profile-{p.id}"
    except Exception:
        slug_val = f"profile-{p.id}"

    return {
        "id":               p.id,
        "user_id":          p.user_id,
        "slug":             slug_val,
        "profile_picture":  pic,              # NOT NULL in DB
        "email":            p.email or "",
        "first_name":       p.first_name or "",
        "last_name":        p.last_name or "",
        "status":           p.status or "",
        "role":             p.role or "",
        "default_store_id": p.default_store_id,
        "telephone":        _str(p.telephone) if getattr(p, "telephone", None) else None,
    }


def _vendor(v) -> dict:
    return {
        "id":           v.id,
        "name":         v.name or "",
        "slug":         _slug(getattr(v, "slug", None)),
        "phone_number": _str(v.phone_number) if v.phone_number else None,
        "address":      v.address or "",
    }


def _customer(c) -> dict:
    return {
        "id":              c.id,
        "first_name":      c.first_name or "",
        "last_name":       c.last_name or "",
        "address":         c.address or "",
        "phone":           c.phone or "",
        "balance":         _float(c.balance),
        "total_invoiced":  _float(c.total_invoiced),
        "total_paid":      _float(c.total_paid),
        "last_updated_at": _str(c.last_updated_at),
    }


def _payment(p) -> dict:
    return {
        "id":              p.id,
        "customer_id":     p.customer_id,
        "date":            _str(p.date),
        "amount":          _float(p.amount),
        "cheque_number":   p.cheque_number or "",
        "remarks":         p.remarks or "",
        "created_by_id":   p.created_by_id,
        "last_updated_at": _str(p.last_updated_at),
    }


def _category(c) -> dict:
    return {
        "id":   c.id,
        "name": c.name or "",
        "slug": _slug(getattr(c, "slug", None)),
    }


def _color(c) -> dict:
    return {
        "id":   c.id,
        "name": c.name or "",
        "slug": _slug(getattr(c, "slug", None)),
    }


def _item(it) -> dict:
    return {
        "id":          it.id,
        "name":        it.name or "",
        "slug":        _slug(getattr(it, "slug", None)),
        "description": it.description or "",
        "category_id": it.category_id,
        "stock":       it.stock or 0,
        "quantity":    it.quantity or 0,
        "price":       _float(it.price),
        "vendor_id":   it.vendor_id,
    }


def _productvariant(v) -> dict:
    return {
        "id":         v.id,
        "product_id": v.product_id,
        "color_id":   v.color_id,
        "sku":        v.sku or "",
        "stock_qty":  v.stock_qty or 0,
    }


def _region(r) -> dict:
    return {
        "id":        r.id,
        "name":      r.name or "",
        "slug":      _slug(getattr(r, "slug", None)),
        "company":   r.company or "",
        "is_active": r.is_active,
    }


def _store(s) -> dict:
    return {
        "id":        s.id,
        "region_id": s.region_id,
        "name":      s.name or "",
        "slug":      _slug(getattr(s, "slug", None)),
        "address":   s.address or "",
        "is_active": s.is_active,
    }


def _storestock(ss) -> dict:
    return {
        "id":       ss.id,
        "store_id": ss.store_id,
        "item_id":  ss.item_id,
        "quantity": ss.quantity,
    }


def _stocktransfer(t) -> dict:
    return {
        "id":            t.id,
        "from_store_id": t.from_store_id,
        "to_store_id":   t.to_store_id,
        "item_id":       t.item_id,
        "quantity":      t.quantity,
        "note":          t.note or "",
        "created_at":    _str(t.created_at),
        "created_by_id": t.created_by_id,
    }


def _invoice(inv) -> dict:
    return {
        "id":              inv.id,
        "uuid":            _str(inv.uuid) if inv.uuid else None,
        "date":            _str(inv.date),
        "last_updated_at": _str(inv.last_updated_at),
        "customer_id":     inv.customer_id,
        "store_id":        inv.store_id,
        "shipping":        _float(inv.shipping),
        "total":           _float(inv.total),
        "grand_total":     _float(inv.grand_total),
    }


def _invoiceitem(ii) -> dict:
    return {
        "id":             ii.id,
        "invoice_id":     ii.invoice_id,
        "item_id":        ii.item_id,
        "quantity":       _float(ii.quantity),
        "price_per_item": _float(ii.price_per_item),
        "discount":       _float(ii.discount),
        "custom_name":    ii.custom_name or "",
    }


def _sale(s) -> dict:
    return {
        "id":             s.id,
        "date_added":     _str(s.date_added),
        "customer_id":    s.customer_id,
        "sub_total":      _float(s.sub_total),
        "grand_total":    _float(s.grand_total),
        "tax_amount":     _float(s.tax_amount),
        "tax_percentage": _float(s.tax_percentage),
        "amount_paid":    _float(s.amount_paid),
        "amount_change":  _float(s.amount_change),
    }


def _saledetail(d) -> dict:
    return {
        "id":           d.id,
        "sale_id":      d.sale_id,
        "item_id":      d.item_id,
        "price":        _float(d.price),
        "quantity":     d.quantity,
        "total_detail": _float(d.total_detail),
    }


def _purchase(p) -> dict:
    return {
        "id":              p.id,
        "uuid":            _str(p.uuid),
        "store_id":        p.store_id,
        "vendor_id":       p.vendor_id,
        "description":     p.description or "",
        "order_date":      _str(p.order_date),
        "delivery_date":   _str(p.delivery_date) if p.delivery_date else None,
        "delivery_status": p.delivery_status or "",
        "price":           _float(p.price),
        "total_value":     _float(p.total_value),
    }


def _purchasedetail(d) -> dict:
    return {
        "id":           d.id,
        "purchase_id":  d.purchase_id,
        "item_id":      d.item_id,
        "color_id":     d.color_id,
        "quantity":     d.quantity,
        "price":        _float(d.price),
        "total_detail": _float(d.total_detail),
    }


def _bill(b) -> dict:
    return {
        "id":               b.id,
        "date":             _str(b.date),
        "institution_name": b.institution_name or "",
        "phone_number":     b.phone_number,
        "email":            b.email or "",
        "address":          b.address or "",
        "description":      b.description or "",
        "payment_details":  b.payment_details or "",
        "amount":           _float(b.amount),
        "status":           b.status,
    }


def _delivery(d) -> dict:
    return {
        "id":            d.id,
        "item_id":       d.item_id,
        "customer_name": d.customer_name or "",
        "phone_number":  _str(d.phone_number) if d.phone_number else None,
        "location":      d.location or "",
        "date":          _str(d.date),
        "is_delivered":  d.is_delivered,
    }


# ── registry ───────────────────────────────────────────────────────────────────

@dataclass
class ModelSpec:
    """
    Describes how one Django model syncs with Supabase.
    table name is always model._meta.db_table — never hardcoded.
    """
    app_label:  str
    model_name: str
    serializer: Callable[[Any], dict]
    queryset:   Callable | None = None

    @property
    def table(self) -> str:
        from django.apps import apps
        return apps.get_model(self.app_label, self.model_name)._meta.db_table

    def get_model(self):
        from django.apps import apps
        return apps.get_model(self.app_label, self.model_name)

    def all_rows(self) -> list[dict]:
        model = self.get_model()
        qs = self.queryset(model) if self.queryset else model.objects.all()
        return [self.serializer(obj) for obj in qs.iterator()]


# Dependency-safe order — parents always before children.
# sync_pendingsync intentionally omitted — never synced to Supabase.
REGISTRY: list[ModelSpec] = [
    # ── auth ──────────────────────────────────────────────────────────────────
    ModelSpec("auth",         "User",           _user),

    # ── accounts ──────────────────────────────────────────────────────────────
    ModelSpec("accounts",     "Vendor",         _vendor),
    ModelSpec("accounts",     "Customer",       _customer),
    ModelSpec("accounts",     "Profile",        _profile),
    ModelSpec("accounts",     "Payment",        _payment),

    # ── store ─────────────────────────────────────────────────────────────────
    ModelSpec("store",        "Category",       _category),
    ModelSpec("store",        "Color",          _color),
    ModelSpec("store",        "Item",           _item),
    ModelSpec("store",        "ProductVariant", _productvariant),
    ModelSpec("store",        "Delivery",       _delivery),

    # ── locations ─────────────────────────────────────────────────────────────
    ModelSpec("locations",    "Region",         _region),
    ModelSpec("locations",    "Store",          _store),
    ModelSpec("locations",    "StoreStock",     _storestock),
    ModelSpec("locations",    "StockTransfer",  _stocktransfer),

    # ── transactions ──────────────────────────────────────────────────────────
    ModelSpec("transactions", "Sale",           _sale),
    ModelSpec("transactions", "SaleDetail",     _saledetail),
    ModelSpec("transactions", "Purchase",       _purchase),
    ModelSpec("transactions", "PurchaseDetail", _purchasedetail),

    # ── invoice ───────────────────────────────────────────────────────────────
    ModelSpec("invoice",      "Invoice",        _invoice),
    ModelSpec("invoice",      "InvoiceItem",    _invoiceitem),

    # ── bills ─────────────────────────────────────────────────────────────────
    ModelSpec("bills",        "Bill",           _bill),
]

# Quick lookups
REGISTRY_MAP: dict[tuple[str, str], ModelSpec] = {
    (s.app_label, s.model_name): s for s in REGISTRY
}

REGISTRY_BY_TABLE: dict[str, ModelSpec] = {}
for _spec in REGISTRY:
    try:
        REGISTRY_BY_TABLE[_spec.table] = _spec
    except Exception:
        pass
