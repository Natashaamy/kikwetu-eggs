CREATE TABLE IF NOT EXISTS customers (
    customer_id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    username TEXT UNIQUE,
    phone_number TEXT UNIQUE NOT NULL,
    password_hash TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admins (
    admin_id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
    product_id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    unit_name TEXT NOT NULL,
    unit_price BIGINT NOT NULL CHECK (unit_price >= 0),
    stock_quantity INTEGER NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0),
    low_stock_threshold INTEGER NOT NULL DEFAULT 10 CHECK (low_stock_threshold >= 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS orders (
    order_id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    order_number TEXT UNIQUE NOT NULL,
    order_status TEXT NOT NULL CHECK (
        order_status IN ('pending', 'confirmed', 'processing', 'completed', 'cancelled')
    ),
    total_amount BIGINT NOT NULL CHECK (total_amount >= 0),
    payment_status TEXT NOT NULL DEFAULT 'unpaid' CHECK (payment_status IN ('unpaid', 'paid')),
    payment_method TEXT CHECK (payment_method IN ('cash', 'mpesa', 'bank_transfer')),
    paid_at TIMESTAMPTZ,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS order_items (
    order_item_id BIGSERIAL PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price BIGINT NOT NULL CHECK (unit_price >= 0),
    line_total BIGINT NOT NULL CHECK (line_total >= 0),
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
        ON UPDATE CASCADE
        ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(product_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id BIGSERIAL PRIMARY KEY,
    order_id BIGINT UNIQUE NOT NULL,
    payment_method TEXT NOT NULL CHECK (payment_method IN ('mpesa', 'cash', 'bank_transfer')),
    payment_status TEXT NOT NULL CHECK (
        payment_status IN ('pending', 'processing', 'paid', 'failed', 'cancelled', 'refunded')
    ),
    amount_due BIGINT NOT NULL CHECK (amount_due >= 0),
    amount_paid BIGINT NOT NULL DEFAULT 0 CHECK (amount_paid >= 0),
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
        ON UPDATE CASCADE
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS mpesa_transactions (
    transaction_id BIGSERIAL PRIMARY KEY,
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    merchant_request_id TEXT,
    checkout_request_id TEXT UNIQUE NOT NULL,
    phone_number TEXT NOT NULL,
    amount BIGINT NOT NULL CHECK (amount > 0),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending', 'successful', 'failed', 'cancelled')
    ),
    result_code TEXT,
    result_description TEXT,
    mpesa_receipt_number TEXT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
        ON UPDATE CASCADE
        ON DELETE CASCADE,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_mpesa_transactions_order_status
ON mpesa_transactions(order_id, status);

CREATE INDEX IF NOT EXISTS idx_mpesa_transactions_customer_id
ON mpesa_transactions(customer_id);

CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_status_created_at ON orders(order_status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_product_id ON order_items(product_id);
CREATE TABLE IF NOT EXISTS farm_expenses (
 id BIGSERIAL PRIMARY KEY, category TEXT NOT NULL CHECK(category IN ('feed','medicine')),
 item_name TEXT NOT NULL, quantity NUMERIC(16,3) NOT NULL CHECK(quantity > 0),
 unit TEXT NOT NULL, unit_price NUMERIC(16,2) NOT NULL CHECK(unit_price >= 0),
 total_amount NUMERIC(20,2) NOT NULL CHECK(total_amount >= 0), purchase_date DATE NOT NULL,
 notes TEXT NOT NULL DEFAULT '', created_by BIGINT NOT NULL,
 submission_key TEXT NOT NULL UNIQUE, submission_payload TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, deleted_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_expenses_date ON farm_expenses(purchase_date, category);
CREATE TABLE IF NOT EXISTS expense_audit (
 id BIGSERIAL PRIMARY KEY, expense_id BIGINT NOT NULL REFERENCES farm_expenses(id),
 action TEXT NOT NULL, snapshot TEXT NOT NULL, changed_by BIGINT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS admin_notifications (
 id BIGSERIAL PRIMARY KEY, event_key TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
 description TEXT NOT NULL, order_id BIGINT REFERENCES orders(order_id),
 created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS notification_reads (
 notification_id BIGINT NOT NULL REFERENCES admin_notifications(id),
 admin_id BIGINT NOT NULL, read_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(notification_id, admin_id)
);

CREATE TABLE IF NOT EXISTS payment_attempts (
 attempt_id TEXT PRIMARY KEY, request_key TEXT NOT NULL UNIQUE,
 order_id BIGINT NOT NULL REFERENCES orders(order_id),
 customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
 amount NUMERIC(16,2) NOT NULL CHECK(amount > 0), phone_number TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('reserved','unknown','pending','resolved','rejected')),
 checkout_request_id TEXT UNIQUE, issue TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_attempt_active ON payment_attempts(order_id)
 WHERE state IN ('reserved','unknown','pending');
CREATE TABLE IF NOT EXISTS payment_callback_inbox (
 event_id TEXT PRIMARY KEY, checkout_request_id TEXT NOT NULL, payload TEXT NOT NULL,
 received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 processed_at TIMESTAMPTZ, issue TEXT, last_attempt_at TIMESTAMPTZ, attempt_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_callback_checkout ON payment_callback_inbox(checkout_request_id, received_at);
CREATE TABLE IF NOT EXISTS payment_verifications (
 transaction_id BIGINT PRIMARY KEY REFERENCES mpesa_transactions(transaction_id),
 callback_received_at TIMESTAMPTZ, provider_paid_at TIMESTAMPTZ, verified_at TIMESTAMPTZ,
 timestamp_source TEXT, last_query_at TIMESTAMPTZ, query_count INTEGER NOT NULL DEFAULT 0,
 issue TEXT
);
CREATE TABLE IF NOT EXISTS payment_events (
 event_id BIGSERIAL PRIMARY KEY,
 order_id BIGINT NOT NULL REFERENCES orders(order_id),
 kind TEXT NOT NULL CHECK(kind IN ('receipt','refund')),
 amount NUMERIC(16,2) NOT NULL CHECK(amount > 0),
 method TEXT NOT NULL CHECK(method IN ('cash','bank_transfer','mpesa')),
 idempotency_key TEXT NOT NULL UNIQUE, reference TEXT NOT NULL,
 occurred_at TIMESTAMPTZ NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 created_by BIGINT REFERENCES admins(admin_id)
);
CREATE INDEX IF NOT EXISTS idx_payment_events_order ON payment_events(order_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_expense_audit_expense ON expense_audit(expense_id);
CREATE INDEX IF NOT EXISTS idx_notifications_page ON admin_notifications(created_at, id);
CREATE INDEX IF NOT EXISTS idx_notification_reads_admin ON notification_reads(admin_id, notification_id);

CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP);
