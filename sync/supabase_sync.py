"""
supabase_sync.py
Uses plain requests (HTTP/1.1) instead of the supabase-py client.
This avoids the HTTP/2 "Server disconnected" issue entirely.

Improved restore_all_from_supabase():
 - Detects tables from Supabase (information_schema) when possible
 - Uses TABLE_MAP to map Supabase table names -> Django model tables
 - Paginates REST queries (handles Supabase 1000-row default)
 - Skips Django internal tables
 - Better logging / error handling
"""
import logging
import requests
from django.conf import settings
from django.db import transaction

logger = logging.getLogger('sync')

BATCH_SIZE = 100
PAGE_SIZE = 1000  # Supabase / PostgREST default page size; we page with Range headers


def _is_sync_enabled():
    return getattr(settings, 'SUPABASE_SYNC_ENABLED', False)


def _headers(extra=None):
    h = {
        'apikey': settings.SUPABASE_KEY,
        'Authorization': f'Bearer {settings.SUPABASE_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'resolution=merge-duplicates',
    }
    if extra:
        h.update(extra)
    return h


def _url(table):
    return f'{settings.SUPABASE_URL}/rest/v1/{table}'


def _queue_pending(operation, table_name, record_id, app_label='', model_name='', local_pk='', error=''):
    try:
        from sync.models import PendingSync
        PendingSync.objects.create(
            operation=operation, table_name=table_name,
            record_id=str(record_id), app_label=app_label,
            model_name=model_name, local_pk=str(local_pk),
            last_error=str(error)[:500],
        )
    except Exception as e:
        logger.error('Failed to queue pending sync: %s', e)


# -- low level ------------------------------------------------------------------

def _post_batch(table, rows):
    """POST a batch of rows. Returns True on success."""
    try:
        r = requests.post(
            _url(table), json=rows, headers=_headers(), timeout=30
        )
        if r.status_code in (200, 201):
            return True
        logger.warning('Supabase %s batch failed: %s %s', table, r.status_code, r.text[:200])
        return False
    except Exception as e:
        logger.warning('Supabase %s batch exception: %s', table, e)
        return False


def _delete_row(table, record_id):
    """DELETE a single row by id."""
    try:
        r = requests.delete(
            _url(table), headers=_headers(),
            params={'id': f'eq.{record_id}'}, timeout=10
        )
        return r.status_code in (200, 204)
    except Exception as e:
        logger.warning('Supabase delete %s id=%s: %s', table, record_id, e)
        return False


def batch_upsert(table, rows):
    """
    Upsert rows in chunks of BATCH_SIZE.
    If a chunk fails, retries one row at a time.
    Returns count of successful rows.
    """
    if not rows:
        return 0
    success = 0
    for i in range(0, len(rows), BATCH_SIZE):
        chunk = rows[i:i + BATCH_SIZE]
        if _post_batch(table, chunk):
            success += len(chunk)
        else:
            # retry one by one
            for row in chunk:
                if _post_batch(table, [row]):
                    success += 1
                else:
                    logger.warning('Row failed permanently %s id=%s', table, row.get('id'))
    return success


def safe_upsert(table, data, app_label='', model_name='', local_pk=''):
    """Single-row upsert used by signals."""
    if not _is_sync_enabled():
        return
    if not _post_batch(table, [data]):
        _queue_pending('upsert', table, data.get('id', ''), app_label, model_name, local_pk, 'post failed')


def safe_delete(table, record_id, app_label='', model_name=''):
    if not _is_sync_enabled():
        return
    if not _delete_row(table, record_id):
        _queue_pending('delete', table, record_id, app_label, model_name, error='delete failed')


# -- per-model signal helpers ---------------------------------------------------

def sync_user(u):
    safe_upsert('auth_users', {'id': u.id, 'username': u.username, 'email': u.email or '',
        'first_name': u.first_name or '', 'last_name': u.last_name or '',
        'is_staff': u.is_staff, 'is_active': u.is_active, 'date_joined': str(u.date_joined)},
        'auth', 'User', u.pk)

def delete_user(pk): safe_delete('auth_users', pk)

def sync_profile(p):
    safe_upsert('accounts_profiles', {'id': p.id, 'user_id': p.user_id, 'email': p.email or '',
        'first_name': p.first_name or '', 'last_name': p.last_name or '',
        'status': p.status or '', 'role': p.role or '', 'default_store_id': p.default_store_id},
        'accounts', 'Profile', p.pk)

def delete_profile(pk): safe_delete('accounts_profiles', pk)

def sync_vendor(v):
    safe_upsert('accounts_vendors', {'id': v.id, 'name': v.name or '',
        'phone_number': str(v.phone_number) if v.phone_number else None, 'address': v.address or ''},
        'accounts', 'Vendor', v.pk)

def delete_vendor(pk): safe_delete('accounts_vendors', pk)

def sync_customer(c):
    safe_upsert('accounts_customers', {'id': c.id, 'first_name': c.first_name or '',
        'last_name': c.last_name or '', 'address': c.address or '', 'phone': c.phone or '',
        'balance': float(c.balance), 'total_invoiced': float(c.total_invoiced),
        'total_paid': float(c.total_paid), 'last_updated_at': str(c.last_updated_at)},
        'accounts', 'Customer', c.pk)

def delete_customer(pk): safe_delete('accounts_customers', pk)

def sync_payment(p):
    safe_upsert('accounts_payments', {'id': p.id, 'customer_id': p.customer_id,
        'date': str(p.date), 'amount': float(p.amount), 'cheque_number': p.cheque_number or '',
        'remarks': p.remarks or '', 'last_updated_at': str(p.last_updated_at)},
        'accounts', 'Payment', p.pk)

def delete_payment(pk): safe_delete('accounts_payments', pk)

def sync_category(c):
    safe_upsert('store_categories', {'id': c.id, 'name': c.name or ''}, 'store', 'Category', c.pk)

def delete_category(pk): safe_delete('store_categories', pk)

def sync_color(c):
    safe_upsert('store_colors', {'id': c.id, 'name': c.name or ''}, 'store', 'Color', c.pk)

def delete_color(pk): safe_delete('store_colors', pk)

def sync_item(it):
    safe_upsert('store_items', {'id': it.id, 'name': it.name or '', 'description': it.description or '',
        'category_id': it.category_id, 'stock': it.stock or 0, 'quantity': it.quantity or 0,
        'price': float(it.price or 0), 'vendor_id': it.vendor_id}, 'store', 'Item', it.pk)

def delete_item(pk): safe_delete('store_items', pk)

def sync_variant(v):
    safe_upsert('store_productvariants', {'id': v.id, 'product_id': v.product_id,
        'color_id': v.color_id, 'sku': v.sku or '', 'stock_qty': v.stock_qty or 0},
        'store', 'ProductVariant', v.pk)

def delete_variant(pk): safe_delete('store_productvariants', pk)

def sync_sale(s):
    safe_upsert('transactions_sales', {'id': s.id, 'date_added': str(s.date_added),
        'customer_id': s.customer_id, 'sub_total': float(s.sub_total),
        'grand_total': float(s.grand_total), 'tax_amount': float(s.tax_amount),
        'tax_percentage': float(s.tax_percentage), 'amount_paid': float(s.amount_paid),
        'amount_change': float(s.amount_change)}, 'transactions', 'Sale', s.pk)

def delete_sale(pk): safe_delete('transactions_sales', pk)

def sync_saledetail(d):
    safe_upsert('transactions_saledetails', {'id': d.id, 'sale_id': d.sale_id,
        'item_id': d.item_id, 'price': float(d.price), 'quantity': d.quantity,
        'total_detail': float(d.total_detail)}, 'transactions', 'SaleDetail', d.pk)

def delete_saledetail(pk): safe_delete('transactions_saledetails', pk)

def sync_purchase(p):
    safe_upsert('transactions_purchases', {'id': p.id, 'uuid': str(p.uuid),
        'store_id': p.store_id, 'vendor_id': p.vendor_id, 'description': p.description or '',
        'order_date': str(p.order_date),
        'delivery_date': str(p.delivery_date) if p.delivery_date else None,
        'delivery_status': p.delivery_status or '', 'total_value': float(p.total_value)},
        'transactions', 'Purchase', p.pk)

def delete_purchase(pk): safe_delete('transactions_purchases', pk)

def sync_purchasedetail(d):
    safe_upsert('transactions_purchasedetails', {'id': d.id, 'purchase_id': d.purchase_id,
        'item_id': d.item_id, 'color_id': d.color_id, 'quantity': d.quantity,
        'price': float(d.price), 'total_detail': float(d.total_detail)},
        'transactions', 'PurchaseDetail', d.pk)

def delete_purchasedetail(pk): safe_delete('transactions_purchasedetails', pk)

def sync_invoice(inv):
    safe_upsert('invoice_invoices', {'id': inv.id, 'uuid': str(inv.uuid) if inv.uuid else None,
        'date': str(inv.date), 'last_updated_at': str(inv.last_updated_at),
        'customer_id': inv.customer_id, 'store_id': inv.store_id,
        'shipping': float(inv.shipping), 'total': float(inv.total),
        'grand_total': float(inv.grand_total)}, 'invoice', 'Invoice', inv.pk)

def delete_invoice(pk): safe_delete('invoice_invoices', pk)

def sync_invoiceitem(ii):
    safe_upsert('invoice_invoiceitems', {'id': ii.id, 'invoice_id': ii.invoice_id,
        'item_id': ii.item_id, 'quantity': float(ii.quantity),
        'price_per_item': float(ii.price_per_item), 'discount': float(ii.discount),
        'custom_name': ii.custom_name or ''}, 'invoice', 'InvoiceItem', ii.pk)

def delete_invoiceitem(pk): safe_delete('invoice_invoiceitems', pk)

def sync_bill(b):
    safe_upsert('bills_bills', {'id': b.id, 'date': str(b.date),
        'institution_name': b.institution_name or '', 'phone_number': b.phone_number,
        'email': b.email or '', 'address': b.address or '', 'description': b.description or '',
        'payment_details': b.payment_details or '', 'amount': float(b.amount), 'status': b.status},
        'bills', 'Bill', b.pk)

def delete_bill(pk): safe_delete('bills_bills', pk)

def sync_region(r):
    safe_upsert('locations_regions', {'id': r.id, 'name': r.name or '',
        'company': r.company or '', 'is_active': r.is_active}, 'locations', 'Region', r.pk)

def delete_region(pk): safe_delete('locations_regions', pk)

def sync_store(s):
    safe_upsert('locations_stores', {'id': s.id, 'region_id': s.region_id,
        'name': s.name or '', 'address': s.address or '', 'is_active': s.is_active},
        'locations', 'Store', s.pk)

def delete_store(pk): safe_delete('locations_stores', pk)

def sync_storestock(ss):
    safe_upsert('locations_storestocks', {'id': ss.id, 'store_id': ss.store_id,
        'item_id': ss.item_id, 'quantity': ss.quantity}, 'locations', 'StoreStock', ss.pk)

def delete_storestock(pk): safe_delete('locations_storestocks', pk)

def sync_stocktransfer(t):
    safe_upsert('locations_stocktransfers', {'id': t.id, 'from_store_id': t.from_store_id,
        'to_store_id': t.to_store_id, 'item_id': t.item_id, 'quantity': t.quantity,
        'note': t.note or '', 'created_at': str(t.created_at), 'created_by_id': t.created_by_id},
        'locations', 'StockTransfer', t.pk)

def delete_stocktransfer(pk): safe_delete('locations_stocktransfers', pk)


# ===============================================================================
# FULL SYNC (push) - keep your original implementation
# ===============================================================================
def sync_all_data():
    if not _is_sync_enabled():
        logger.info('Supabase sync not enabled - skipping.')
        return

    try:
        from sync.models import PendingSync
        deleted, _ = PendingSync.objects.all().delete()
        if deleted:
            logger.info('Cleared %d stale pending entries.', deleted)
    except Exception as e:
        logger.warning('Could not clear PendingSync: %s', e)

    from django.contrib.auth import get_user_model
    from accounts.models import Profile, Vendor, Customer, Payment
    from store.models import Category, Color, Item, ProductVariant
    from transactions.models import Sale, SaleDetail, Purchase, PurchaseDetail
    from invoice.models import Invoice, InvoiceItem
    from bills.models import Bill
    from locations.models import Region, Store, StoreStock, StockTransfer

    User = get_user_model()

    def rows(qs, fn):
        return [fn(obj) for obj in qs.iterator()]

    tasks = [
        ('auth_users',                   rows(User.objects.all(), lambda u: {
            'id': u.id, 'username': u.username, 'email': u.email or '',
            'first_name': u.first_name or '', 'last_name': u.last_name or '',
            'is_staff': u.is_staff, 'is_active': u.is_active, 'date_joined': str(u.date_joined)})),
        ('accounts_vendors',             rows(Vendor.objects.all(), lambda v: {
            'id': v.id, 'name': v.name or '',
            'phone_number': str(v.phone_number) if v.phone_number else None, 'address': v.address or ''})),
        ('accounts_customers',           rows(Customer.objects.all(), lambda c: {
            'id': c.id, 'first_name': c.first_name or '', 'last_name': c.last_name or '',
            'address': c.address or '', 'phone': c.phone or '', 'balance': float(c.balance),
            'total_invoiced': float(c.total_invoiced), 'total_paid': float(c.total_paid),
            'last_updated_at': str(c.last_updated_at)})),
        ('store_categories',             rows(Category.objects.all(), lambda c: {'id': c.id, 'name': c.name or ''})),
        ('store_colors',                 rows(Color.objects.all(), lambda c: {'id': c.id, 'name': c.name or ''})),
        ('bills_bills',                  rows(Bill.objects.all(), lambda b: {
            'id': b.id, 'date': str(b.date), 'institution_name': b.institution_name or '',
            'phone_number': b.phone_number, 'email': b.email or '', 'address': b.address or '',
            'description': b.description or '', 'payment_details': b.payment_details or '',
            'amount': float(b.amount), 'status': b.status})),
        ('locations_regions',            rows(Region.objects.all(), lambda r: {
            'id': r.id, 'name': r.name or '', 'company': r.company or '', 'is_active': r.is_active})),
        ('accounts_profiles',            rows(Profile.objects.all(), lambda p: {
            'id': p.id, 'user_id': p.user_id, 'email': p.email or '',
            'first_name': p.first_name or '', 'last_name': p.last_name or '',
            'status': p.status or '', 'role': p.role or '', 'default_store_id': p.default_store_id})),
        ('store_items',                  rows(Item.objects.all(), lambda it: {
            'id': it.id, 'name': it.name or '', 'description': it.description or '',
            'category_id': it.category_id, 'stock': it.stock or 0, 'quantity': it.quantity or 0,
            'price': float(it.price or 0), 'vendor_id': it.vendor_id})),
        ('locations_stores',             rows(Store.objects.all(), lambda s: {
            'id': s.id, 'region_id': s.region_id, 'name': s.name or '',
            'address': s.address or '', 'is_active': s.is_active})),
        ('store_productvariants',        rows(ProductVariant.objects.all(), lambda v: {
            'id': v.id, 'product_id': v.product_id, 'color_id': v.color_id,
            'sku': v.sku or '', 'stock_qty': v.stock_qty or 0})),
        ('accounts_payments',            rows(Payment.objects.all(), lambda p: {
            'id': p.id, 'customer_id': p.customer_id, 'date': str(p.date),
            'amount': float(p.amount), 'cheque_number': p.cheque_number or '',
            'remarks': p.remarks or '', 'last_updated_at': str(p.last_updated_at)})),
        ('transactions_sales',           rows(Sale.objects.all(), lambda s: {
            'id': s.id, 'date_added': str(s.date_added), 'customer_id': s.customer_id,
            'sub_total': float(s.sub_total), 'grand_total': float(s.grand_total),
            'tax_amount': float(s.tax_amount), 'tax_percentage': float(s.tax_percentage),
            'amount_paid': float(s.amount_paid), 'amount_change': float(s.amount_change)})),
        ('locations_storestocks',        rows(StoreStock.objects.all(), lambda ss: {
            'id': ss.id, 'store_id': ss.store_id, 'item_id': ss.item_id, 'quantity': ss.quantity})),
        ('transactions_saledetails',     rows(SaleDetail.objects.all(), lambda d: {
            'id': d.id, 'sale_id': d.sale_id, 'item_id': d.item_id,
            'price': float(d.price), 'quantity': d.quantity, 'total_detail': float(d.total_detail)})),
        ('transactions_purchases',       rows(Purchase.objects.all(), lambda p: {
            'id': p.id, 'uuid': str(p.uuid), 'store_id': p.store_id, 'vendor_id': p.vendor_id,
            'description': p.description or '', 'order_date': str(p.order_date),
            'delivery_date': str(p.delivery_date) if p.delivery_date else None,
            'delivery_status': p.delivery_status or '', 'total_value': float(p.total_value)})),
        ('invoice_invoices',             rows(Invoice.objects.all(), lambda inv: {
            'id': inv.id, 'uuid': str(inv.uuid) if inv.uuid else None,
            'date': str(inv.date), 'last_updated_at': str(inv.last_updated_at),
            'customer_id': inv.customer_id, 'store_id': inv.store_id,
            'shipping': float(inv.shipping), 'total': float(inv.total),
            'grand_total': float(inv.grand_total)})),
        ('transactions_purchasedetails', rows(PurchaseDetail.objects.all(), lambda d: {
            'id': d.id, 'purchase_id': d.purchase_id, 'item_id': d.item_id,
            'color_id': d.color_id, 'quantity': d.quantity,
            'price': float(d.price), 'total_detail': float(d.total_detail)})),
        ('invoice_invoiceitems',         rows(InvoiceItem.objects.all(), lambda ii: {
            'id': ii.id, 'invoice_id': ii.invoice_id, 'item_id': ii.item_id,
            'quantity': float(ii.quantity), 'price_per_item': float(ii.price_per_item),
            'discount': float(ii.discount), 'custom_name': ii.custom_name or ''})),
        ('locations_stocktransfers',     rows(StockTransfer.objects.all(), lambda t: {
            'id': t.id, 'from_store_id': t.from_store_id, 'to_store_id': t.to_store_id,
            'item_id': t.item_id, 'quantity': t.quantity, 'note': t.note or '',
            'created_at': str(t.created_at), 'created_by_id': t.created_by_id})),
    ]

    for table, row_list in tasks:
        count = batch_upsert(table, row_list)
        logger.info('Synced %d / %d  %s', count, len(row_list), table)

    logger.info('Full sync complete.')


# ===============================================================================
# RESTORE (pull) - improved implementation
# ===============================================================================

# Map Django db_table -> Supabase table name when they differ.
# Keep this mapping updated with any additional table name differences you have.
TABLE_MAP = {
    # django_db_table: supabase_table
    "Customers": "accounts_customers",
    "Payments": "accounts_payments",
    "accounts_profile": "accounts_profiles",
    "accounts_vendor": "accounts_vendors",

    "store_category": "store_categories",
    "store_color": "store_colors",
    "store_item": "store_items",
    "store_productvariant": "store_productvariants",

    "sales": "transactions_sales",
    "sale_details": "transactions_saledetails",
    "transactions_purchase": "transactions_purchases",
    "purchase_details": "transactions_purchasedetails",

    "invoice_invoice": "invoice_invoices",
    "invoice_invoiceitem": "invoice_invoiceitems",

    "bills_bill": "bills_bills",

    "locations_region": "locations_regions",
    "locations_store": "locations_stores",
    "locations_storestock": "locations_storestocks",
    "locations_stocktransfer": "locations_stocktransfers",

    "auth_user": "auth_users",
    # add more mappings if needed
}

# Order matters: list of supabase table names in dependency-safe order
RESTORE_ORDER = [
    "auth_users",
    "accounts_vendors",
    "accounts_profiles",
    "accounts_customers",
    "accounts_payments",

    "store_categories",
    "store_colors",
    "store_items",
    "store_productvariants",

    "locations_regions",
    "locations_stores",
    "locations_storestocks",
    "locations_stocktransfers",

    "transactions_sales",
    "transactions_saledetails",
    "transactions_purchases",
    "transactions_purchasedetails",

    "invoice_invoices",
    "invoice_invoiceitems",

    "bills_bills",
]


# Supabase/internal tables we never want to restore into Django models:
EXCLUDED_SUPABASE_TABLES = {
    "django_migrations",
    "django_content_type",
    "django_session",
    "django_admin_log",
    "auth_permission",
    "auth_group_permissions",
    "auth_user_groups",
    "auth_user_user_permissions",
    # add any other Supabase-only tables you want to ignore
}


def _get_supabase_table_list():
    """
    Try to query information_schema.tables via PostgREST (Supabase REST).
    If that fails (403 / endpoint not exposed), return the list from TABLE_MAP values.
    """
    info_url = f"{settings.SUPABASE_URL}/rest/v1/information_schema.tables"
    headers = _headers()
    params = {"select": "table_name", "table_schema": "public"}  # PostgREST query params
    try:
        r = requests.get(info_url, headers=headers, params=params, timeout=20)
        if r.status_code == 200:
            data = r.json()
            tables = [t.get("table_name") for t in data if t.get("table_name")]
            # Filter out system tables
            tables = [t for t in tables if t not in EXCLUDED_SUPABASE_TABLES]
            if tables:
                print("Detected Supabase tables via information_schema:", len(tables))
                return tables
        else:
            logger.info("Could not fetch information_schema.tables (status=%s). Falling back to TABLE_MAP.", r.status_code)
    except Exception as e:
        logger.warning("Failed to query information_schema.tables: %s. Falling back to TABLE_MAP.", e)

    # fallback: use known mapping values (and unique)
    fallback = sorted({v for v in TABLE_MAP.values()})
    print("Using fallback Supabase table list from TABLE_MAP:", fallback)
    return fallback


def _fetch_supabase_rows(table):
    """
    Fetch all rows from a Supabase table using paged requests with Range headers.
    Returns list of rows (dicts).
    """
    url = f"{settings.SUPABASE_URL}/rest/v1/{table}"
    all_rows = []
    start = 0
    while True:
        end = start + PAGE_SIZE - 1
        extra = {"Range": f"{start}-{end}"}  # PostgREST Range header for pagination
        try:
            r = requests.get(url, headers=_headers(extra), params={"select": "*"}, timeout=30)
        except Exception as e:
            logger.warning("Supabase fetch %s exception: %s", table, e)
            return all_rows

        if r.status_code not in (200, 206):
            logger.warning("Supabase fetch %s returned %s: %s", table, r.status_code, r.text[:200])
            return all_rows

        try:
            rows = r.json()
        except Exception as e:
            logger.warning("Failed to decode JSON for %s: %s", table, e)
            return all_rows

        if not rows:
            break

        all_rows.extend(rows)

        # If we received fewer rows than page size, we've reached the end
        if len(rows) < PAGE_SIZE:
            break

        start += PAGE_SIZE

    return all_rows


def restore_all_from_supabase():
    """
    Improved restore:
    1. Detect supabase tables (information_schema or fallback)
    2. For each supabase table, find a Django model (via TABLE_MAP or model._meta.db_table)
    3. Fetch all rows (paged) and restore into the model.
    """
    from django.apps import apps

    if not getattr(settings, "SUPABASE_KEY", None) or not getattr(settings, "SUPABASE_URL", None):
        print("Supabase credentials not configured - aborting.")
        return

    print("\n🔎 Detecting Supabase tables...\n")
    supabase_tables = _get_supabase_table_list()
    if not supabase_tables:
        print("No Supabase tables detected - aborting.")
        return

    models = list(apps.get_models())

    # Build reverse table map: supabase_table -> django_model
    supabase_to_model = {}
    for m in models:
        dj_table = m._meta.db_table
        sup_table = TABLE_MAP.get(dj_table, dj_table)  # prefer mapping, else assume names match
        if sup_table in supabase_tables and sup_table not in EXCLUDED_SUPABASE_TABLES:
            supabase_to_model[sup_table] = m

    # Also include any supabase table names that match model.db_table exactly
    for m in models:
        dj_table = m._meta.db_table
        if dj_table in supabase_tables and dj_table not in EXCLUDED_SUPABASE_TABLES:
            supabase_to_model.setdefault(dj_table, m)

    if not supabase_to_model:
        print("No matching Django models for Supabase tables found. Check TABLE_MAP.")
        return

    print("Will restore the following Supabase -> Django model mappings:")
    for sup_table, model in supabase_to_model.items():
        print(f"  {sup_table} -> {model._meta.app_label}.{model.__name__}")

    # Restore tables in dependency-safe order (only process tables we actually mapped)
    for sup_table in RESTORE_ORDER:
        model = supabase_to_model.get(sup_table)
        if not model:
            # skip sup_table if there's no model mapping / it's not present in Supabase
            continue

        print(f"\nFetching {sup_table} ...")
        rows = _fetch_supabase_rows(sup_table)
        if not rows:
            print(f"⚠️ {sup_table} → no data found")
            continue

        print(f"🔄 Restoring {sup_table} ({len(rows)} rows) -> {model._meta.db_table}")

        restored = 0
        errors = 0

        # We perform updates inside a transaction for consistency.
        # For very large tables you may want to chunk and/or use a bulk-upsert strategy.
        with transaction.atomic():
            for row in rows:
                try:
                    pk = row.get("id")
                    if pk is not None:
                        # Use update_or_create to preserve existing rows
                        model.objects.update_or_create(id=pk, defaults=row)
                    else:
                        model.objects.create(**row)
                    restored += 1
                except Exception as e:
                    errors += 1
                    logger.warning("Failed to restore row into %s: %s (row id=%s)", model._meta.db_table, e, row.get("id"))

        print(f"✅ Loaded {restored} rows into {model._meta.db_table} (errors: {errors})")

    print("\n🎉 Restore finished\n")