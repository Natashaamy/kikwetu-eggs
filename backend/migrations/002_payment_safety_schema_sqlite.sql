
CREATE TABLE IF NOT EXISTS payment_attempts (
 attempt_id TEXT PRIMARY KEY, request_key TEXT NOT NULL UNIQUE,
 order_id BIGINT NOT NULL REFERENCES orders(order_id),
 customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
 amount NUMERIC(16,2) NOT NULL CHECK(amount > 0), phone_number TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('reserved','unknown','pending','resolved','rejected')),
 checkout_request_id TEXT UNIQUE, issue TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_attempt_active ON payment_attempts(order_id)
 WHERE state IN ('reserved','unknown','pending');
CREATE TABLE IF NOT EXISTS payment_callback_inbox (
 event_id TEXT PRIMARY KEY, checkout_request_id TEXT NOT NULL, payload TEXT NOT NULL,
 received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 processed_at TEXT, issue TEXT, last_attempt_at TEXT, attempt_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_callback_checkout ON payment_callback_inbox(checkout_request_id, received_at);
CREATE TABLE IF NOT EXISTS payment_verifications (
 transaction_id BIGINT PRIMARY KEY REFERENCES mpesa_transactions(transaction_id),
 callback_received_at TEXT, provider_paid_at TEXT, verified_at TEXT,
 timestamp_source TEXT, last_query_at TEXT, query_count INTEGER NOT NULL DEFAULT 0,
 issue TEXT
);
CREATE TABLE IF NOT EXISTS payment_events (
 event_id INTEGER PRIMARY KEY,
 order_id BIGINT NOT NULL REFERENCES orders(order_id),
 kind TEXT NOT NULL CHECK(kind IN ('receipt','refund')),
 amount NUMERIC(16,2) NOT NULL CHECK(amount > 0),
 method TEXT NOT NULL CHECK(method IN ('cash','bank_transfer','mpesa')),
 idempotency_key TEXT NOT NULL UNIQUE, reference TEXT NOT NULL,
 occurred_at TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 created_by BIGINT REFERENCES admins(admin_id)
);
CREATE INDEX IF NOT EXISTS idx_payment_events_order ON payment_events(order_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_expense_audit_expense ON expense_audit(expense_id);
CREATE INDEX IF NOT EXISTS idx_notifications_page ON admin_notifications(created_at, id);
CREATE INDEX IF NOT EXISTS idx_notification_reads_admin ON notification_reads(admin_id, notification_id);

CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
