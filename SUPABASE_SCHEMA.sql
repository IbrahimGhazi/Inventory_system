-- ============================================================
-- NAUGHTYFISH – Supabase Schema
-- Run this entire file in Supabase → SQL Editor → New query
-- ============================================================

-- ── auth_users ────────────────────────────────────────────────────────────────
create table if not exists auth_users (
    id          bigint primary key,
    username    text not null,
    email       text default '',
    first_name  text default '',
    last_name   text default '',
    is_staff    boolean default false,
    is_active   boolean default true,
    date_joined text
);

-- ── accounts_profiles ─────────────────────────────────────────────────────────
create table if not exists accounts_profiles (
    id               bigint primary key,
    user_id          bigint references auth_users(id) on delete cascade,
    email            text default '',
    first_name       text default '',
    last_name        text default '',
    status           text default '',
    role             text default '',
    default_store_id bigint
);

-- ── accounts_vendors ──────────────────────────────────────────────────────────
create table if not exists accounts_vendors (
    id           bigint primary key,
    name         text not null,
    phone_number text,
    address      text default ''
);

-- ── accounts_customers ────────────────────────────────────────────────────────
create table if not exists accounts_customers (
    id              bigint primary key,
    first_name      text not null,
    last_name       text default '',
    address         text default '',
    phone           text default '',
    balance         numeric(12,2) default 0,
    total_invoiced  numeric(12,2) default 0,
    total_paid      numeric(12,2) default 0,
    last_updated_at text
);

-- ── accounts_payments ─────────────────────────────────────────────────────────
create table if not exists accounts_payments (
    id              bigint primary key,
    customer_id     bigint references accounts_customers(id) on delete cascade,
    date            text,
    amount          numeric(12,2) not null,
    cheque_number   text default '',
    remarks         text default '',
    last_updated_at text
);

-- ── store_categories ──────────────────────────────────────────────────────────
create table if not exists store_categories (
    id   bigint primary key,
    name text not null
);

-- ── store_colors ──────────────────────────────────────────────────────────────
create table if not exists store_colors (
    id   bigint primary key,
    name text not null
);

-- ── store_items ───────────────────────────────────────────────────────────────
create table if not exists store_items (
    id          bigint primary key,
    name        text not null,
    description text default '',
    category_id bigint references store_categories(id) on delete set null,
    stock       integer default 0,
    quantity    integer default 0,
    price       numeric(12,2) default 0,
    vendor_id   bigint references accounts_vendors(id) on delete set null
);

-- ── store_productvariants ─────────────────────────────────────────────────────
create table if not exists store_productvariants (
    id         bigint primary key,
    product_id bigint references store_items(id) on delete cascade,
    color_id   bigint references store_colors(id) on delete restrict,
    sku        text default '',
    stock_qty  integer default 0
);

-- ── transactions_sales ────────────────────────────────────────────────────────
create table if not exists transactions_sales (
    id             bigint primary key,
    date_added     text,
    customer_id    bigint references accounts_customers(id) on delete set null,
    sub_total      numeric(12,2) default 0,
    grand_total    numeric(12,2) default 0,
    tax_amount     numeric(12,2) default 0,
    tax_percentage numeric(10,4) default 0,
    amount_paid    numeric(12,2) default 0,
    amount_change  numeric(12,2) default 0
);

-- ── transactions_saledetails ──────────────────────────────────────────────────
create table if not exists transactions_saledetails (
    id           bigint primary key,
    sale_id      bigint references transactions_sales(id) on delete cascade,
    item_id      bigint references store_items(id) on delete set null,
    price        numeric(12,2) default 0,
    quantity     integer default 0,
    total_detail numeric(12,2) default 0
);

-- ── locations_regions ────────────────────────────────────────────────────────
create table if not exists locations_regions (
    id        bigint primary key,
    name      text not null,
    company   text default '',
    is_active boolean default true
);

-- ── locations_stores ─────────────────────────────────────────────────────────
create table if not exists locations_stores (
    id        bigint primary key,
    region_id bigint references locations_regions(id) on delete protect,
    name      text not null,
    address   text default '',
    is_active boolean default true
);

-- ── transactions_purchases ────────────────────────────────────────────────────
create table if not exists transactions_purchases (
    id               bigint primary key,
    uuid             text,
    store_id         bigint references locations_stores(id) on delete set null,
    vendor_id        bigint references accounts_vendors(id) on delete cascade,
    description      text default '',
    order_date       text,
    delivery_date    text,
    delivery_status  text default 'S',
    total_value      numeric(12,2) default 0
);

-- ── transactions_purchasedetails ──────────────────────────────────────────────
create table if not exists transactions_purchasedetails (
    id           bigint primary key,
    purchase_id  bigint references transactions_purchases(id) on delete cascade,
    item_id      bigint references store_items(id) on delete set null,
    color_id     bigint references store_colors(id) on delete set null,
    quantity     integer default 0,
    price        numeric(12,2) default 0,
    total_detail numeric(12,2) default 0
);

-- ── invoice_invoices ──────────────────────────────────────────────────────────
create table if not exists invoice_invoices (
    id              bigint primary key,
    uuid            text,
    date            text,
    last_updated_at text,
    customer_id     bigint references accounts_customers(id) on delete cascade,
    store_id        bigint references locations_stores(id) on delete set null,
    shipping        numeric(12,2) default 0,
    total           numeric(12,2) default 0,
    grand_total     numeric(12,2) default 0
);

-- ── invoice_invoiceitems ──────────────────────────────────────────────────────
create table if not exists invoice_invoiceitems (
    id              bigint primary key,
    invoice_id      bigint references invoice_invoices(id) on delete cascade,
    item_id         bigint references store_items(id) on delete set null,
    quantity        numeric(12,2) default 0,
    price_per_item  numeric(12,2) default 0,
    discount        numeric(6,2)  default 0,
    custom_name     text default ''
);

-- ── bills_bills ───────────────────────────────────────────────────────────────
create table if not exists bills_bills (
    id               bigint primary key,
    date             text,
    institution_name text not null,
    phone_number     bigint,
    email            text default '',
    address          text default '',
    description      text default '',
    payment_details  text not null,
    amount           numeric(12,2) not null,
    status           boolean default false
);

-- ── locations_storestocks ─────────────────────────────────────────────────────
create table if not exists locations_storestocks (
    id       bigint primary key,
    store_id bigint references locations_stores(id) on delete cascade,
    item_id  bigint references store_items(id) on delete cascade,
    quantity integer default 0
);

-- ── locations_stocktransfers ──────────────────────────────────────────────────
create table if not exists locations_stocktransfers (
    id            bigint primary key,
    from_store_id bigint references locations_stores(id) on delete restrict,
    to_store_id   bigint references locations_stores(id) on delete restrict,
    item_id       bigint references store_items(id) on delete restrict,
    quantity      integer default 0,
    note          text default '',
    created_at    text,
    created_by_id bigint references auth_users(id) on delete set null
);

-- ============================================================
-- OPTIONAL: Enable Row Level Security (recommended)
-- Uncomment below if you want to restrict read access.
-- ============================================================
-- alter table accounts_customers enable row level security;
-- create policy "Public read" on accounts_customers for select using (true);

