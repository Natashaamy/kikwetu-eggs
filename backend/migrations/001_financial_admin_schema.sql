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
