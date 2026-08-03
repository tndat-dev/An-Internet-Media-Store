-- =====================================================================
-- IMPLEMENTATION NOTES (read first)
-- ---------------------------------------------------------------------
-- The LIVE schema is defined by Django migrations under
-- Programming/backend/apps/*/migrations and is the SOURCE OF TRUTH.
-- This file is the design reference, reconciled to the implemented
-- "best-of-both" schema. Differences kept on purpose:
--
--   * carts / cart_items tables exist in the implementation (apps.carts)
--     but were missing from this design file — added at the bottom.
--   * orders.status DEFAULT is PENDING_PAYMENT (an order starts awaiting
--     payment), not PENDING_PROCESSING. orders also has cart_id (FK to
--     carts) to support the draft-order flow.
--   * payment_transactions is gateway-oriented (see rewritten table
--     below): it references orders(order_id), stores the provider
--     `gateway` (PAYPAL/VIETQR) plus provider_order_id / capture_id /
--     refund_id / transaction_reference / provider_payload (JSONB), and
--     uses payment_status_enum value SUCCESS (not COMPLETED). The
--     separate payment_method_enum (QR_CODE/CREDIT_CARD) is NOT used by
--     the implementation; the provider gateway field replaces it.
--   * Product subtype tables are simplified to scalar columns in code
--     (e.g. books.authors / cds.tracklist / dvds.subtitles are text, not
--     JSONB; cover_type/disc_type have no DB CHECK). The richer design
--     columns remain documented here as the intended model.
--   * users.password_hash is nullable/blank in code (no auth/login UI is
--     built yet; rows are created for action attribution only).
--   * updated_at is maintained by Django (auto_now) instead of SQL
--     triggers; the trigger definitions below are design reference.
--
-- All other tables/constraints match the implementation.
-- TODO(team): regenerate ERD.png / DatabaseDesign.png / DatabaseDescription
-- from this reconciled model (Astah/dbdiagram) — images are not auto-synced.
-- =====================================================================

--CREATE DATABASE aimsdb;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS product_histories CASCADE;
DROP TABLE IF EXISTS newspapers CASCADE;
DROP TABLE IF EXISTS dvds CASCADE;
DROP TABLE IF EXISTS cds CASCADE;
DROP TABLE IF EXISTS books CASCADE;
DROP TABLE IF EXISTS refund_transactions CASCADE;
DROP TABLE IF EXISTS payment_transactions CASCADE;
DROP TABLE IF EXISTS invoices CASCADE;
DROP TABLE IF EXISTS delivery_infos CASCADE;
DROP TABLE IF EXISTS order_items CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS user_roles CASCADE;
DROP TABLE IF EXISTS roles CASCADE;
DROP TABLE IF EXISTS users CASCADE;

DROP TYPE IF EXISTS user_status_enum CASCADE;
DROP TYPE IF EXISTS product_type_enum CASCADE;
DROP TYPE IF EXISTS product_status_enum CASCADE;
DROP TYPE IF EXISTS history_action_type_enum CASCADE;
DROP TYPE IF EXISTS order_status_enum CASCADE;
DROP TYPE IF EXISTS payment_status_enum CASCADE;
DROP TYPE IF EXISTS payment_method_enum CASCADE;
DROP TYPE IF EXISTS refund_status_enum CASCADE;
DROP TYPE IF EXISTS refund_method_enum CASCADE;

-- ENUM TYPE
CREATE TYPE user_status_enum AS ENUM (
    'ACTIVE',
    'DEACTIVATED',
    'BLOCKED'
);

CREATE TYPE product_type_enum AS ENUM (
    'BOOK',
    'CD',
    'DVD',
    'NEWSPAPER'
);

CREATE TYPE product_status_enum AS ENUM (
    'ACTIVE',
    'DEACTIVATED',
    'DELETED'
);

CREATE TYPE history_action_type_enum AS ENUM (
    'CREATE',
    'UPDATE',
    'DELETE',
    'DEACTIVATE',
    'STOCK_ADJUST'
);

CREATE TYPE order_status_enum AS ENUM (
	'PENDING_PAYMENT',
    'PENDING_PROCESSING',
    'APPROVED',
    'REJECTED',
    'CANCELLED'
);

CREATE TYPE payment_status_enum AS ENUM (
    'PENDING',
    'SUCCESS',
    'FAILED',
    'CANCELLED',
    'REFUNDED'
);

CREATE TYPE payment_method_enum AS ENUM (
    'QR_CODE',
    'CREDIT_CARD'
);

CREATE TYPE refund_status_enum AS ENUM (
    'PENDING',
    'SUCCESS',
    'FAILED',
    'MANUAL_REQUIRED'
);

CREATE TYPE refund_method_enum AS ENUM (
    'PAYPAL_API',
    'MANUAL_BANK_TRANSFER'
);


-- common updated_at trigger function
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- USER & ROLE TABLES
CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL,
    password_hash TEXT NOT NULL,
    status user_status_enum NOT NULL DEFAULT 'ACTIVE',

    CONSTRAINT uq_users_username UNIQUE (username),
    CONSTRAINT uq_users_email UNIQUE (email)
);

CREATE TABLE roles (
    role_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_name VARCHAR(100) NOT NULL,
    description TEXT,

    CONSTRAINT uq_roles_role_name UNIQUE (role_name)
);

CREATE TABLE user_roles (
    user_id UUID NOT NULL,
    role_id UUID NOT NULL,

    PRIMARY KEY (user_id, role_id),
    CONSTRAINT fk_user_roles_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_user_roles_role FOREIGN KEY (role_id) REFERENCES roles(role_id) ON DELETE CASCADE
);


-- PRODUCT TABLES
CREATE TABLE products (
    product_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_type product_type_enum NOT NULL,
    title VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    general_description TEXT,
    height NUMERIC(10, 2) NOT NULL DEFAULT 0,
    width NUMERIC(10, 2) NOT NULL DEFAULT 0,
    length NUMERIC(10, 2) NOT NULL DEFAULT 0,
    weight NUMERIC(10, 2) NOT NULL DEFAULT 0,
    barcode VARCHAR(100) NOT NULL,
    original_value NUMERIC(14, 2) NOT NULL,
    current_price NUMERIC(14, 2) NOT NULL,
    stock_quantity INTEGER NOT NULL DEFAULT 0,
    status product_status_enum NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_products_barcode UNIQUE (barcode),
    CONSTRAINT ck_products_dimensions_non_negative CHECK (height >= 0 AND width >= 0 AND length >= 0 AND weight >= 0),
    CONSTRAINT ck_products_original_value_non_negative CHECK (original_value >= 0),
    CONSTRAINT ck_products_current_price_non_negative CHECK (current_price >= 0),
    CONSTRAINT ck_products_price_lower_bound CHECK (current_price >= original_value * 0.30),
    CONSTRAINT ck_products_price_upper_bound CHECK (current_price <= original_value * 1.50),
    CONSTRAINT ck_products_stock_non_negative CHECK (stock_quantity >= 0),
    CONSTRAINT ck_products_deleted_only_when_stock_zero CHECK (status <> 'DELETED' OR stock_quantity = 0)
);

CREATE TRIGGER trg_products_updated_at
BEFORE UPDATE ON products
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TABLE books (
    product_id UUID PRIMARY KEY,
    authors JSONB NOT NULL,
    cover_type VARCHAR(50) NOT NULL,
    publisher VARCHAR(255) NOT NULL,
    publication_date DATE NOT NULL,
    number_of_pages INTEGER,
    language VARCHAR(100),
    genre VARCHAR(100),

    CONSTRAINT fk_books_product FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE,
    CONSTRAINT ck_books_number_of_pages_positive CHECK (number_of_pages IS NULL OR number_of_pages > 0),
    CONSTRAINT ck_books_cover_type CHECK (cover_type IN ('PAPERBACK', 'HARDCOVER'))
);

CREATE TABLE cds (
    product_id UUID PRIMARY KEY,
    artists JSONB NOT NULL,
    record_label VARCHAR(255) NOT NULL,
    tracks JSONB NOT NULL,
    genre VARCHAR(100) NOT NULL,
    release_date DATE,

    CONSTRAINT fk_cds_product FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
);

CREATE TABLE dvds (
    product_id UUID PRIMARY KEY,
    disc_type VARCHAR(50) NOT NULL,
    director VARCHAR(255) NOT NULL,
    runtime INTEGER NOT NULL,
    studio VARCHAR(255) NOT NULL,
    language VARCHAR(100) NOT NULL,
    subtitles JSONB NOT NULL,
    release_date DATE,
    genre VARCHAR(100),

    CONSTRAINT fk_dvds_product FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE,
    CONSTRAINT ck_dvds_runtime_positive CHECK (runtime > 0),
    CONSTRAINT ck_dvds_disc_type CHECK (disc_type IN ('BLU_RAY', 'HD_DVD'))
);

CREATE TABLE newspapers (
    product_id UUID PRIMARY KEY,
    editor_in_chief VARCHAR(255) NOT NULL,
    publisher VARCHAR(255) NOT NULL,
    publication_date DATE NOT NULL,
    issue_number VARCHAR(100),
    publication_frequency VARCHAR(100),
    issn VARCHAR(100),
    language VARCHAR(100),
    sections JSONB,

    CONSTRAINT fk_newspapers_product FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
);

CREATE TABLE product_histories (
    history_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL,
    performed_by UUID NOT NULL,
    action_type history_action_type_enum NOT NULL,
    action_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    old_value_snapshot JSONB,
    new_value_snapshot JSONB,
    reason TEXT,

    CONSTRAINT fk_product_histories_product FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE,
    CONSTRAINT fk_product_histories_performed_by FOREIGN KEY (performed_by) REFERENCES users(user_id) ON DELETE RESTRICT,
    CONSTRAINT ck_product_histories_stock_adjust_reason
        CHECK (
            action_type <> 'STOCK_ADJUST'
            OR reason IS NOT NULL
        )
);


-- ORDER TABLES
CREATE TABLE orders (
    order_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    processed_by UUID,
    status order_status_enum NOT NULL DEFAULT 'PENDING_PAYMENT',  -- impl: starts awaiting payment
    total_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
    order_view_token UUID NOT NULL DEFAULT gen_random_uuid(),
    cancel_token UUID NOT NULL DEFAULT gen_random_uuid(),
    processed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_orders_processed_by FOREIGN KEY (processed_by) REFERENCES users(user_id) ON DELETE SET NULL,
    CONSTRAINT ck_orders_total_amount_non_negative CHECK (total_amount >= 0),
    CONSTRAINT uq_orders_order_view_token UNIQUE (order_view_token),
    CONSTRAINT uq_orders_cancel_token UNIQUE (cancel_token)
);

CREATE TRIGGER trg_orders_updated_at
BEFORE UPDATE ON orders
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TABLE order_items (
    order_item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL,
    product_id UUID NOT NULL,
    product_title VARCHAR(255) NOT NULL,
    unit_price NUMERIC(14, 2) NOT NULL,
    quantity INTEGER NOT NULL,
    line_amount_excl_vat NUMERIC(14, 2) NOT NULL,
    line_amount_incl_vat NUMERIC(14, 2) NOT NULL,

    CONSTRAINT fk_order_items_order FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE,
    CONSTRAINT fk_order_items_product FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE RESTRICT,
    CONSTRAINT ck_order_items_unit_price_non_negative CHECK (unit_price >= 0),
    CONSTRAINT ck_order_items_quantity_positive CHECK (quantity > 0),
    CONSTRAINT ck_order_items_line_excl_non_negative CHECK (line_amount_excl_vat >= 0),
    CONSTRAINT ck_order_items_line_incl_non_negative CHECK (line_amount_incl_vat >= 0),
    CONSTRAINT uq_order_items_order_product UNIQUE (order_id, product_id)
);

CREATE TABLE delivery_infos (
    delivery_info_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL,
    customer_name VARCHAR(255) NOT NULL,
    phone_number VARCHAR(30) NOT NULL,
    email VARCHAR(255) NOT NULL,
    delivery_address TEXT NOT NULL,
    delivery_province VARCHAR(100) NOT NULL,
    delivery_instructions TEXT,
    expected_date DATE,
    shipping_fee NUMERIC(14, 2) NOT NULL DEFAULT 0,

    CONSTRAINT fk_delivery_infos_order FOREIGN KEY (order_id) 
		REFERENCES orders(order_id) ON DELETE CASCADE,
    CONSTRAINT uq_delivery_infos_order UNIQUE (order_id),
    CONSTRAINT ck_delivery_infos_shipping_fee_non_negative CHECK (shipping_fee >= 0)
);

CREATE TABLE invoices (
    invoice_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL,
    total_product_price_excl_vat NUMERIC(14, 2) NOT NULL DEFAULT 0,
    vat_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
    total_product_price_incl_vat NUMERIC(14, 2) NOT NULL DEFAULT 0,
    delivery_fee NUMERIC(14, 2) NOT NULL DEFAULT 0,
    total_amount_to_pay NUMERIC(14, 2) NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_invoices_order FOREIGN KEY (order_id)
        REFERENCES orders(order_id) ON DELETE CASCADE,
		
    CONSTRAINT uq_invoices_order UNIQUE (order_id),
    CONSTRAINT ck_invoices_total_product_excl_non_negative CHECK (total_product_price_excl_vat >= 0),
    CONSTRAINT ck_invoices_vat_non_negative CHECK (vat_amount >= 0),
    CONSTRAINT ck_invoices_total_product_incl_non_negative CHECK (total_product_price_incl_vat >= 0),
    CONSTRAINT ck_invoices_delivery_fee_non_negative CHECK (delivery_fee >= 0),
    CONSTRAINT ck_invoices_total_amount_to_pay_non_negative CHECK (total_amount_to_pay >= 0),
    CONSTRAINT ck_invoices_total_product_incl_formula CHECK (total_product_price_incl_vat = total_product_price_excl_vat + vat_amount),
    CONSTRAINT ck_invoices_total_amount_formula CHECK (total_amount_to_pay = total_product_price_incl_vat + delivery_fee)
);

CREATE TRIGGER trg_invoices_updated_at
BEFORE UPDATE ON invoices
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();


-- PAYMENT & REFUND TABLES
-- NOTE: reconciled to the implementation (gateway-oriented; references orders).
-- Django uses a BIGINT auto id PK here, not a UUID. `gateway` replaces the
-- design's payment_method; provider_* / transaction_reference / provider_payload
-- carry per-provider data. status uses SUCCESS (not COMPLETED).
CREATE TABLE payment_transactions (
    id BIGSERIAL PRIMARY KEY,
    order_id UUID NOT NULL,
    gateway VARCHAR(20) NOT NULL,                 -- PAYPAL | VIETQR
    provider_order_id VARCHAR(128) DEFAULT '',
    capture_id VARCHAR(128) DEFAULT '',
    refund_id VARCHAR(128) DEFAULT '',
    transaction_reference VARCHAR(64) DEFAULT '', -- VietQR content/match code
    provider_payload JSONB NOT NULL DEFAULT '{}', -- e.g. qr_payload, qr_image_url
    transaction_content TEXT DEFAULT '',
    amount NUMERIC(14, 2) NOT NULL,
    currency VARCHAR(10) NOT NULL DEFAULT 'VND',
    status payment_status_enum NOT NULL DEFAULT 'PENDING',
    note TEXT DEFAULT '',
    transaction_datetime TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_payment_transactions_order FOREIGN KEY (order_id)
        REFERENCES orders(order_id) ON DELETE RESTRICT,

    CONSTRAINT ck_payment_transactions_amount_non_negative CHECK (amount >= 0)
);

-- NOTE: payment_transaction_id is BIGINT (payment_transactions.id) in the
-- implementation; Django uses a BIGINT auto id PK for refund rows too.
CREATE TABLE refund_transactions (
    id BIGSERIAL PRIMARY KEY,
    payment_transaction_id BIGINT NOT NULL,
    refund_amount NUMERIC(14, 2) NOT NULL,
    refund_reason TEXT NOT NULL,
    refund_datetime TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    refund_status refund_status_enum NOT NULL DEFAULT 'PENDING',
    refund_method refund_method_enum NOT NULL,
    manual_refund_note TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_refund_transactions_payment_transaction FOREIGN KEY (payment_transaction_id)
        REFERENCES payment_transactions(id) ON DELETE RESTRICT,

    CONSTRAINT ck_refund_transactions_amount_non_negative CHECK (refund_amount >= 0),

    CONSTRAINT ck_refund_transactions_manual_note_required
        CHECK (
            refund_method <> 'MANUAL_BANK_TRANSFER'
            OR manual_refund_note IS NOT NULL
        )
);


-- INDEXES
CREATE INDEX idx_product_histories_product_id ON product_histories(product_id);
CREATE INDEX idx_product_histories_performed_by ON product_histories(performed_by);
CREATE INDEX idx_orders_processed_by ON orders(processed_by);
CREATE INDEX idx_order_items_order_id ON order_items(order_id);
CREATE INDEX idx_order_items_product_id ON order_items(product_id);
CREATE INDEX idx_delivery_infos_order_id ON delivery_infos(order_id);
CREATE INDEX idx_invoices_order_id ON invoices(order_id);
CREATE INDEX idx_payment_transactions_order_id ON payment_transactions(order_id);
CREATE INDEX idx_payment_transactions_transaction_reference ON payment_transactions(transaction_reference);
CREATE INDEX idx_refund_transactions_payment_transaction_id ON refund_transactions(payment_transaction_id);


-- =====================================================================
-- CARTS (present in the implementation, apps.carts; absent from the
-- original design). Appended here so the reference matches the live DB.
-- =====================================================================
CREATE TABLE carts (
    cart_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cart_token VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'OPEN',   -- OPEN | CHECKED_OUT
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_carts_cart_token UNIQUE (cart_token)
);

CREATE TABLE cart_items (
    cart_item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cart_id UUID NOT NULL,
    product_id UUID NOT NULL,
    quantity INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_cart_items_cart FOREIGN KEY (cart_id) REFERENCES carts(cart_id) ON DELETE CASCADE,
    CONSTRAINT fk_cart_items_product FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE RESTRICT,
    CONSTRAINT uq_cart_items_cart_product UNIQUE (cart_id, product_id)
);

-- orders.cart_id (FK to carts) exists in the implementation; added here
-- after carts is defined to keep execution order valid.
ALTER TABLE orders ADD COLUMN cart_id UUID;
ALTER TABLE orders ADD CONSTRAINT fk_orders_cart
    FOREIGN KEY (cart_id) REFERENCES carts(cart_id) ON DELETE SET NULL;