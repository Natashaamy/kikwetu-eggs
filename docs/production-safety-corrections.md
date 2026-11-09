# Kikwetu Eggs — production safety corrections

9 November 2026. **Classification: READY FOR STAGING VERIFICATION. Not approved for production.**

The locally reproduced payment, reporting, session and migration defects have corrections and regression coverage. PostgreSQL integration and real Daraja verification are mandatory release gates and have not run. No deployment, production migration, production-data access, real payment or refund was performed.

## Verification

| Check | Result | Scope |
|---|---|---|
| Full backend suite | 124 discovered: **119 passed, 5 skipped**, 53.816 seconds | SQLite/local unit and API tests; includes the original 78 tests and 41 new regression tests |
| PostgreSQL integration suite | **5 skipped** | No isolated database configured; includes migration preservation, drift, rollback and competing payment operations |
| Browser suite | **10 passed**, 41.3 seconds | Real Chrome, mocked API; includes two new payment-safety workflows |
| Vite production build | **Passed**, 64 modules, 1.61 seconds | Compilation, not hosting verification |
| Migration preservation probe | **Passed twice** | SHA-256 of complete rows across seven legacy business tables unchanged |
| Original failure probes | Rerun; corrected outcomes saved | [Evidence](production-safety-evidence.json), [probe](../backend/audit_readiness.py) |

The initial browser sandbox could not run esbuild in earlier verification; the expanded suite and build used the approved local execution outside that sandbox. No network provider call was made by tests. Test logs remain ignored local files (`safety-tests.log`, `safety-regression-tests.log`).

The original probe used a cash-refund record in the scenario labelled “refunded M-Pesa,” which was ambiguous when combined with a separate M-Pesa receipt. The updated probe explicitly identifies that legacy refund as M-Pesa. It also uses an alphanumeric receipt and an attempt creation date preceding the delayed provider timestamp. Separate regression tests cover mixed cash/M-Pesa receipts, legacy M-Pesa refunds, malformed dates, and independent new refund events. The original evidence is retained rather than rewritten.

## Corrections and before/after evidence

| Audit issue | Corrected behavior | Local verification |
|---|---|---|
| Sandbox-only configuration | Explicit `sandbox`/`production` base URLs and validated PayBill/BuyGoods transaction type. Default remains sandbox; no live credentials used. | Environment-selection tests; real merchant contract still unverified |
| Partial-payment overcharge | Server computes remaining balance from recorded receipts/refunds under the order lock. Whole-shilling requirement rejects fractional balances rather than rounding up. | KES 200 order less KES 100 receipt requests KES 100 |
| Initiation retries and ambiguous timeouts | Unique intent commits before external request. One active intent per order. Same customer request key returns the existing attempt. Timeout/crash reservations block new payment, editing and cash selection. Explicit provider rejection permits a new attempt. | Durable-intent, timeout, rejection and idempotency tests |
| Lost/early callbacks | Callback inbox commits before verification. Early callbacks replay after checkout registration. Customer status queries and a bounded worker query persisted checkouts through authenticated STK Query. | Outage/replay, early callback and missed-callback tests |
| Duplicate callbacks/receipts | Inbox digest, checkout/receipt uniqueness and locked transitions prevent repeated money. Receipt conflict returns 409 and remains flagged; ordinary status polling cannot bypass the conflict. | Serial/concurrent SQLite duplicates and cross-order receipt conflict tests |
| Cash/payment race | All relevant mutations lock the order first. Cash selection rechecks pending intents and conditionally updates only unpaid orders. Network calls hold no order lock. | SQLite competing cash/callback tests; PostgreSQL test supplied but skipped |
| Financial calculations | Shared receipt/refund accounting; manual completion records only the remaining balance in a new immutable event. Mixed cash/M-Pesa receipts add; overlapping legacy M-Pesa summaries do not. | Partial completion, decimals, refunds, mixed receipts, excess amounts, dashboards and report tests |
| Revoked admin session | Central authorization revalidates current admin existence/activity on each protected request and clears rejected sessions. | Deactivated/deleted admin checks across old and new route families |
| Payment timestamp | Valid provider occurrence time converted from Nairobi to UTC; callback receipt and verification times stored separately. Missing/inconsistent time uses a labelled fallback and reconciliation issue. Late callback can enrich a query-confirmed payment without adding money. | Nairobi midnight/year boundary, malformed date and delayed callback tests |
| Migration drift | Frozen SQL files, checksum ledger, pre/post column/default/PK/unique/FK/check/index validation, transactional DDL, PostgreSQL advisory lock and bounded DDL timeouts. Incompatible structures fail clearly. | SQLite missing column/constraint/table, checksum and repeat/preservation tests; PostgreSQL execution pending |

An authenticated STK **initiation** response never marks an order paid. An authenticated STK **status-query success** confirms the stored checkout amount and can settle a missed callback. It does not supply a fabricated receipt or occurrence timestamp. Missing details remain explicitly flagged for reconciliation.

## Financial definitions and legacy data

- `confirmed_payments_received`: gross recorded receipts whose occurrence/verification date falls in the selected Nairobi period, including receipts for cancelled orders that still represent real money.
- `refunds_paid`: recorded completed refunds dated in the period. `POST /api/orders/<id>/refunds` records an already executed refund; it never initiates a provider transfer. Amount, reference and idempotency key are required, and the amount cannot exceed net receipts.
- `paid_orders_amount`: receipts less refunds in the period for non-cancelled orders, including partial receipts. The UI retains its “Paid Orders” label and explains the definition.
- `unpaid_orders_amount`: current remaining collectible balance of non-cancelled orders created during the selected period, floored at zero. It is a creation-period cohort, not an historical accounts-receivable closing balance. Refunds on still-active orders reopen that balance; returned/cancelled business must have its order cancellation handled explicitly.
- `net_cash_balance`: gross receipts minus refunds minus feed and medicine expense totals. It is not accounting profit.
- New manual receipts/refunds are `payment_events`. Successful STK rows are M-Pesa receipt evidence. A legacy cash/bank `payments` row is independent; a legacy M-Pesa `payments` row overlapping successful STK transactions is a summary, not additional money.
- Legacy payment statuses `paid`, `processing` and `refunded` with positive `amount_paid` are counted as recorded receipts; pending/failed/cancelled payment amounts are not. Legacy refunded rows reverse `amount_paid`, using `updated_at` because no historical refund date exists. Confirm that convention against historical records in staging.
- Order paid flags alone are **not** receipts. No automatic ledger backfill invents historic money. Legacy paid orders without evidence, missing receipt dates, ambiguous mixed-method summaries, and refund dates require reconciliation before production sign-off. Undated records are exposed in `undated_payment_records` and excluded from date-period cash totals.
- Admin dashboard, customer outstanding balance, and the legacy report's payment totals use the same receipt rules. Operational completed-order value/product-sales metrics remain order-value metrics, not cash accounting.

Use Decimal arithmetic in all payment calculations. Financial API amounts are decimal strings (some legacy summary endpoints retain integers for whole amounts); no float arithmetic is used to calculate balances.

## Database changes and preservation

No existing business-table column is removed or changed, and migrations do not update/delete customer, admin, order, item, product, payment or STK rows.

The original four financial/admin tables remain. New frozen migration `002_payment_safety` adds:

| Table | Purpose and safeguards |
|---|---|
| `payment_attempts` | UUID text PK; unique customer-scoped request key and nullable checkout ID; order/customer FKs; positive Decimal amount; constrained state; creation/update timestamps; unique partial index allows one reserved/unknown/pending intent per order |
| `payment_callback_inbox` | Payload digest PK, checkout ID, payload text, receipt/processing/last-attempt times, attempt count and issue; checkout/time index; intentionally permits early unmatched callbacks |
| `payment_verifications` | STK transaction PK/FK; provider time, callback receipt time, verification time, timestamp provenance, query backoff state and reconciliation issue |
| `payment_events` | PK; order FK and nullable creating-admin FK; constrained receipt/refund kind and method; positive NUMERIC(16,2) amount; unique idempotency key; reference and occurrence/creation times; order/time index |
| `schema_migrations` | Version PK, SQL checksum and application time; validated like other required structures |

Additional indexes cover expense audit lookups, notification pagination and per-admin reads. Defaults/types/checks/foreign keys/unique constraints are validated against frozen engine-native reference schemas, not inferred from `IF NOT EXISTS`. PostgreSQL validation creates temporary reference relations and requires TEMP privileges; deployment migration role also needs the intended schema's DDL privileges. Additional compatible columns/constraints are allowed; missing required definitions are rejected. Existing legacy non-unique indexes must exist at post-validation; missing old indexes not supplied by these frozen migrations cause rollback and require a reviewed remediation.

Administrator relationships were reviewed: new payment events have an administrator FK. The older expense creator/editor/read identifiers retain their original logical references, avoiding a destructive SQLite table rebuild or an unreviewed constraint over historical orphan IDs. Active-account authorization protects new writes, and these audit identities must not be deleted or reassigned. Orphan inspection and the retention policy remain staging sign-off items; physical FKs were not silently claimed for those older fields.

`migrate_financial_admin.py` runs statement-by-statement inside one transaction, including SQLite (no implicit `executescript` commit). PostgreSQL uses one advisory transaction lock, five-second lock timeout and sixty-second statement timeout. Migration content is frozen in `backend/migrations`; do not edit an applied file. The legacy snapshot is a validation contract, not a script to rebuild existing business tables.

## Recovery operations and unresolved cases

Run `python reconcile_payments.py` from `backend` against a separately approved staging environment, then schedule regular bounded batches after authorized release. The worker handles up to 50 pending checkouts plus 50 matching inbox events per invocation. Recovery queries back off up to 30 minutes; failures do not imply payment failure. Monitor oldest pending intent, oldest unprocessed callback, verification conflicts and query latency. Choose a schedule/worker timeout that accommodates the measured batch duration; avoid unbounded overlapping jobs.

An initiation can lose its response after the provider accepted it. Without a checkout ID, STK Query cannot safely identify that request. Such `reserved`/`unknown` intents deliberately remain blocked. An operator must reconcile the merchant's records using the saved intent/customer/amount/time, obtain evidence of the actual outcome and use a separately reviewed recovery procedure. **Never release a reservation merely because time elapsed.** There is no automatic “assume failed” or blind re-initiation path. A contradictory late success after a provider-confirmed failure can arrive after a new prompt was already accepted; preserve all receipts, flag overpayment and reconcile/refund through an approved process. No automatic refund is issued.

Public Daraja callback metadata is not cryptographically authenticated by this application. Success is independently checked using the checkout's authenticated query, and metadata must match amount/phone/merchant and unique receipt. The STK query does not independently authenticate a supplied receipt string or timestamp. Confirm Safaricom's current contract and any provider-supported callback ingress controls in staging. The [Safaricom-owned library documentation](https://github.com/safaricom/mpesa-node-library/blob/master/README.md) identifies STK Query by checkout ID and distinguishes the separate Transaction Status API, which needs a transaction ID. The current public Daraja query page could not be retrieved; no unsupported automatic lookup from an unknown intent was invented.

## Remaining production gates

1. Run the five PostgreSQL tests on the production major version, using only an isolated staging database. Export `PGTEST_DATABASE_URL` securely and set `PGTEST_CONFIRM_ISOLATED=1`. Tests create/drop random `kikwetu_test_*` schemas only. Do not set these against production. Verify full row preservation, constraints, DDL rollback, permissions and concurrent requests.
2. Verify sandbox Daraja initiation/query/callback contracts, supported final result codes, merchant type, receipt authenticity controls and delayed/missing callbacks. Any real production payment or provider credential change needs separate authorization.
3. Reconcile legacy paid flags/receipts/refunds and administrator audit identities. Confirm the documented financial definitions with the business owner.
4. Verify restored backups, Render Linux runtime/worker settings, migration role, scheduled recovery execution and operational handling of unknown intents. Test existing Netlify/Render domains, cookies, CORS and SPA redirects.
5. Measure realistic report, customer-order and notification-polling load. Queries still aggregate history; notification history refresh behavior and process-local rate limiting remain earlier operational limitations. No dedicated DB readiness endpoint was added.
6. Review the prior npm audit's two moderate package entries. Its SSR advisory is inapplicable to the current declarative SPA; no exploitable open-redirect path was demonstrated. No dependencies were upgraded and no comprehensive Python vulnerability scan was performed.

`APP_ENV=production` now refuses startup without PostgreSQL configuration, a stable secret and HTTPS settings. Provider HTTP timeout is eight seconds per call (OAuth plus request/query can take approximately sixteen seconds); durable storage survives worker loss, but Linux hosting timing still needs verification.

## Files changed in this correction pass

- Backend configuration/security: `.env.example`, `app/__init__.py`, `app/auth.py`.
- Payment/accounting: `app/services/mpesa.py`, new `payment_records.py` and `payment_reconciliation.py`; `app/routes/mpesa_payments.py`, `orders.py`, `customer_portal.py`, `dashboard.py`, `reports.py`, `financial_summary.py`; new `reconcile_payments.py`.
- Database: `schema.sql`, `schema_sqlite.sql`, `migrate_financial_admin.py`; new `app/schema_validation.py` and six frozen SQL files under `migrations/`.
- Tests/evidence: `tests/test_financial_admin.py` fixtures, new `tests/test_payment_safety.py`, new `tests/test_postgres_safety.py`, `audit_readiness.py`, `docs/production-safety-evidence.json`.
- Frontend: `src/api/payments.js`, `src/pages/MyOrdersPage.jsx`, `src/pages/ReportsPage.jsx`, `tests/workflows.spec.js`.
- Documentation: this report, `production-readiness-audit.md`, archived pre-correction audit, `deployment-checklist.md`, `financial-admin-implementation.md`, and root `README.md`.

The repository already contained implementation changes before this pass. This list identifies correction work; it does not attribute the entire existing Git diff to this audit.
