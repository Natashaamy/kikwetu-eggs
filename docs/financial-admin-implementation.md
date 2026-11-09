# Current status

The safety corrections supersede the original payment, reporting, migration and verification descriptions. See [production-safety-corrections.md](production-safety-corrections.md) and [deployment-checklist.md](deployment-checklist.md). Status: **READY FOR STAGING VERIFICATION**, not production. Original implementation history follows.

# Kikwetu Eggs implementation notes

## Audit and root causes

- `MyOrdersPage.jsx` rendered success banners directly from React Router history state. That state survives refresh. Payment polling stopped after six attempts (30 seconds), leaving older payment state on screen. Action alerts had no consistent lifetime or dismiss control.
- Customer order queries included cancelled orders. Cancellation already retained records and restored inventory, but the administrator delete endpoint could permanently erase cancelled order/payment history.
- Customer screens printed raw database timestamps; several admin screens appended `Z` even to PostgreSQL timestamps that already contained an offset. Browser-local timezone formatting caused additional differences. Old report filters grouped by UTC calendar date.
- The dashboard already exposed active and total product counts. Its display combined those values instead of presenting a clear active-product metric.
- Reports treated an order's creation date as its payment date and summed whole-order flags. There was no farm expense model or persistent admin inbox. The existing `payments` table can represent partial amounts, although current checkout forms accept full payment only.
- Public M-Pesa callbacks had no independent provider verification. Initiation checked for a pending request before acquiring an order lock. Callback success was idempotent for serial delivery, but PostgreSQL processing lacked row locking.

## Phases and changed files

1. **Audit:** inspected existing routes, schemas, UI, authentication, payment service and regression tests. Findings are recorded above. No production data was accessed.
2. **Customer fixes:** `MyOrdersPage`, the customer order/dashboard routes, shared `TemporaryMessage`, shared `utils/format`, and existing page alert/date usages. Consume navigation state once; expire successes after four seconds and errors after eight; provide dismissal; refresh authoritative order data every five seconds and clean up on navigation. Cancelled orders stay out of customer lists. Admin deletion now returns 409. Nairobi formatting handles both legacy UTC and offset-aware timestamps. Payment service/callback changes verify results through Daraja's authenticated STK query API, lock writes, reject mismatched metadata and preserve late receipts for reconciliation.
3. **Dashboard/reports:** `DashboardPage`, `ReportsPage`, `financial_summary.py`, and legacy `reports.py`. Total Products displays the active database count. Six financial cards support Monday–Sunday weeks, calendar months and custom inclusive Nairobi dates. Existing CSV timestamps/date filters also use Nairobi. Server-priced order totals cannot be overwritten through the admin API; new admin draft orders start at zero and acquire totals through their existing item endpoint.
4. **Expenses:** `FarmExpensesPage`, `adminFinance.js`, `farm_expenses.py`, both schema files and `migrate_financial_admin.py`. Feed/medicine calculators accept custom names, validate server-side and compute rounded Decimal totals. Idempotency keys prevent duplicate saves, including retry after a lost response. Edit/delete operations retain audit snapshots; deletion is soft. History supports category/date filtering and stored weekly/monthly totals. Money uses PostgreSQL NUMERIC and SQLite numeric affinity, with Decimal arithmetic and bounded values; PostgreSQL decimals are serialized without converting to floating point.
5. **Admin inbox:** `AdminNotifications`, `PortalLayout`, `AdminSidebar`, `notifications.py`, order/payment hooks and schema additions. Events cover orders, payments, cancellations, low stock, payment service/configuration failures and reconciliation. Unique event keys prevent duplicates; reads are stored separately per admin. The bell polls every 30 seconds, supports older notifications, individual/all read actions and links to the existing order detail dialog. Historical events are reconciled from business records on refresh.
6. **Verification:** backend regression tests in `test_financial_admin.py` and `test_mpesa.py`; Chrome workflow tests in `frontend/tests/workflows.spec.js`; existing backend tests and Vite production build. Responsive expense/report screenshots are generated under ignored `frontend/test-results/` and reviewed visually. No existing business database was migrated during testing.

## Reporting definitions and migration (updated)

Recorded receipts and completed refunds determine cash totals; paid-order flags alone do not. Independent cash/bank and M-Pesa receipts add, while overlapping legacy M-Pesa summaries are not added twice. New manual receipt/refund events retain their own amount, time, reference and idempotency key. Net cash subtracts refunds and farm expenses. Cancelled orders have no collectible balance, but their real receipts/refunds remain cash movements. See the correction audit for period/cohort definitions and historical reconciliation requirements.

Use frozen, validated additive migrations after an isolated PostgreSQL rehearsal and restored-backup check. `python migrate_financial_admin.py` checks required structures before and after versioned SQL, stores checksums, and fails on drift. SQLite preservation passed; PostgreSQL tests remain skipped without isolated infrastructure. Do not run production migrations or deploy without separate authorization.

Schedule `python reconcile_payments.py` only on the approved environment. It queries existing checkouts and retries retained callbacks; it never initiates payments or refunds. Unknown initiation outcomes without checkout IDs require merchant reconciliation and must not be automatically released.

See the deployment checklist for environment variables, Linux commands, monitoring and rollback. The prior every-start initializer is no longer recommended for the existing service.

The original local `.venv` referenced a missing Python interpreter. Verification used a separate ignored `.test-venv`, leaving the old environment intact.

## Verification limits (updated)

Full backend suite: 119 passed and 5 PostgreSQL integration tests skipped (124 discovered). Browser suite: 10 passed. Production Vite build passed. Tests use disposable local data and mocked provider calls. No production infrastructure, real payment, deployment or production migration was used. Real PostgreSQL, Daraja, hosting, cookies, recovery scheduling, historical data reconciliation and restore testing remain mandatory staging gates.
