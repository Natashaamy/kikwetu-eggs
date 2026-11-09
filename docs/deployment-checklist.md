# Kikwetu Eggs — Netlify and Render deployment checklist

**Status: READY FOR STAGING VERIFICATION; production remains blocked by the infrastructure gates in [the correction audit](production-safety-corrections.md).** This is a future operator checklist, not an instruction already executed. No deploy, production migration, secret changes or live payment are authorized by the audit request.

## 1. Release approval and staging preparation

- [x] Implement local safety corrections and rerun backend/browser/build checks: 119 backend tests passed, 5 PostgreSQL tests skipped; 10 browser tests and the build passed.
- [ ] Run the skipped PostgreSQL tests and real-provider/hosting checks before production approval.
- [ ] Review dependency advisories and document fixes or applicability acceptance.
- [ ] Identify the existing Render service/database and Netlify site, actual repo root, deploy branch and current release SHAs. Do not create replacement services or databases by assumption.
- [ ] Confirm automatic deployments will not publish an unreviewed push. Stage/review changes on a branch that does not trigger the live services. The working tree contains uncommitted implementation files and new files that must all be included in the approved release.
- [ ] Pin/test the intended Linux Python and Node runtimes. This audit used Python 3.12 and Node 24.18.0 locally; Chrome is required for the current Playwright `channel: chrome` tests. `npm ci` needs development dependencies to build Vite.
- [ ] Prepare a separate PostgreSQL staging database on the production major version, with production-like constraints/data volumes and controlled anonymized data. Do not point audit scripts at production. Perform migration, API, concurrency and cookie tests against staging.
- [ ] Capture the currently deployed frontend/backend SHAs and establish a rollback owner/window.

Render can auto-deploy commits on its linked branch, and supports pre-deploy commands for supported services. Check the existing service's settings and plan rather than assuming those facilities are available. [Render deployment documentation](https://render.com/docs/deploys).

## 2. Environment variables to verify without exposing values

| Location | Name | Required value/behavior |
|---|---|---|
| Render backend | `APP_ENV` | Set `production` on Render to enforce required PostgreSQL, stable-secret and HTTPS configuration at startup. |
| Render backend | `DATABASE_URL` | Existing intended Render PostgreSQL database connection; no SQLite fallback in production. Use the documented internal connection when appropriate for that service/region and verify SSL/network requirements. Never paste it into frontend variables or logs. |
| Render backend | `SECRET_KEY` | Strong stable secret shared across backend workers/restarts. Rotation invalidates existing sessions and needs a deliberate plan. |
| Render backend | `FRONTEND_URL` | Exact canonical frontend HTTPS origin, e.g. `https://<existing-site>.netlify.app` or its custom domain; no path, wildcard or comma-separated list. Staging uses its separate allowed origin. |
| Render backend | `FLASK_HTTPS` | Exactly `1`; enables Secure/HttpOnly/SameSite=None cookies and trusted-proxy IP handling. |
| Render runtime | `PORT` | Provided by Render; start command must bind `0.0.0.0:$PORT`. Not a frontend variable. |
| Render backend | `MPESA_ENV` | Keep `sandbox` for staging. Code supports `production`, but do not switch the live service until provider and release gates pass. |
| Render backend | `MPESA_CONSUMER_KEY`, `MPESA_CONSUMER_SECRET` | Server-only credentials for the explicitly selected Daraja environment/application. |
| Render backend | `MPESA_SHORTCODE`, `MPESA_PASSKEY` | Server-only merchant/environment configuration; validate PayBill/Till and transaction type with provider. Set `MPESA_TRANSACTION_TYPE=CustomerPayBillOnline` or `CustomerBuyGoodsOnline` according to the verified merchant contract. |
| Render backend | `MPESA_TRANSACTION_TYPE` | Validated merchant type: `CustomerPayBillOnline` (default) or `CustomerBuyGoodsOnline`. Verify the correct type in staging. |
| Render backend | `MPESA_CALLBACK_URL` | Public HTTPS Render/backend URL ending `/api/payments/mpesa/callback`, reachable by provider without browser/session authentication. No Netlify HTML redirect or interactive login in its path. |
| Render backend, optional bootstrap | `INITIAL_ADMIN_NAME`, `INITIAL_ADMIN_USERNAME`, `INITIAL_ADMIN_EMAIL`, `INITIAL_ADMIN_PASSWORD` | All four only when intentionally creating the initial admin. For this existing system, normally leave unset; remove after bootstrap. The additive migration does not need these. |
| Render backend, recovery only | `RESET_ADMIN_USERNAME`, `RESET_ADMIN_PASSWORD` | **Unset for routine deployment.** The old `init_db.py` start path resets the matching password on each boot while these remain configured. |
| Netlify frontend, build scope | `VITE_API_URL` | Canonical Render/backend HTTPS **origin**, e.g. `https://<existing-service>.onrender.com`, without `/api`; client helpers append `/api/...`. Requires rebuilding to change. Not localhost. |

No new expense, notification or timezone secret is required. `DATABASE` is a Flask configuration key, not an environment variable read by this application. Do not assume copying `.env.example` to `.env` configures a direct `python migrate_financial_admin.py` process: this script does not call `load_dotenv`. Export/inject configuration explicitly. Never put passwords, connection URLs, Daraja secrets or the Flask session secret into a `VITE_*` variable: those values reach browser code. [Vite environment documentation](https://vite.dev/guide/env-and-mode).

## 3. PostgreSQL rehearsal and backup gate

- [ ] Check `current_database()`, `current_schema()`, PostgreSQL version, server timezone and database role using read-only staging queries; verify the intended target and search path before any future migration.
- [ ] Compare actual columns/types/defaults/checks/FKs/unique constraints/indexes with the schema inventory in the audit. Inspect pre-existing new table names and legacy duplicate/pending payment attempts.
- [ ] Record complete row fingerprints/counts for `customers`, `admins`, `products`, `orders`, `order_items`, `payments` and `mpesa_transactions` on the isolated staging snapshot. Counts alone cannot prove preservation.
- [ ] Run the reviewed migration twice in staging. Verify the four original financial/admin tables and five safety/version tables plus their required indexes exist, no business rows changed, and the second run is harmless.
- [ ] Verify PostgreSQL transactional rollback with a controlled failing staging migration, DDL permissions, lock behavior/timeouts and concurrent startup protection. Do not test injected failure on production.
- [ ] Exercise expense create/edit/soft-delete/idempotent retry, Decimal serialization, FK errors, notification pagination/read state and reporting against real PostgreSQL.
- [ ] Securely configure `PGTEST_DATABASE_URL` for the isolated staging database and `PGTEST_CONFIRM_ISOLATED=1`, then run `python -m unittest discover -s tests -p test_postgres_safety.py -v`. The five integration tests create/drop only random `kikwetu_test_*` schemas. Never configure them against production.
- [ ] Confirm TEMP privileges for PostgreSQL engine-native schema validation, schema DDL privileges, the production major version, and the exact search path.
- [ ] Run concurrent duplicate callbacks, multiple STK attempts, cash selection versus callback, and cancellation versus callback. Verify one authoritative state and complete receipt history.
- [ ] Before any separately authorized production run, create a restorable backup and prove restoration into a separate database. Confirm the existing Render database's actual recovery plan; recovery availability is not universal. [Render backup documentation](https://render.com/docs/postgresql-backups).

Current frozen, validated additive migration command, **only after the above gates and explicit deployment authorization**:

```sh
# Working directory: backend; DATABASE_URL must already target the approved database.
python migrate_financial_admin.py
```

Prefer a reviewed one-time release/pre-deploy migration with appropriate privileges. Do not include a production migration in a Netlify build or ordinary test command. A post-migration code rollback should retain the additive tables and all new financial/audit data; never drop them as a routine rollback. Restoring an old database backup can lose legitimate intervening writes and requires separate incident approval.

## 4. Existing Render backend settings

For the Git root inspected in this audit, `backend/` and `frontend/` are direct children. Local folder name `ChickenBusinesssystem` is not automatically a repository subdirectory. Verify the connected repository layout.

| Setting | If Render Root Directory is `backend` | If Render Root Directory is the repository root |
|---|---|---|
| Build | `pip install -r requirements.txt` | `pip install -r backend/requirements.txt` |
| Reviewed pre-deploy/manual migration | `python migrate_financial_admin.py` | `cd backend && python migrate_financial_admin.py` |
| Base start command | `gunicorn --bind 0.0.0.0:$PORT "app:create_app()"` | `cd backend && gunicorn --bind 0.0.0.0:$PORT "app:create_app()"` |

These start commands are templates, not a finalized worker/timeout policy. Provider calls now use eight-second timeouts (OAuth plus request/query can approach sixteen seconds). Test the complete HTTP timeout and worker budget under failures; choose workers within database capacity and use shared rate-limit storage if needed. Test the same settings on Linux staging. Use the start command without `init_db.py` after confirming all required legacy migrations have been applied. Do not inadvertently rerun admin recovery logic. [Render Flask guidance](https://render.com/docs/deploy-flask).

- [ ] Configure a scheduled `python reconcile_payments.py` job in `backend` using the same approved database and Daraja environment. It queries existing checkouts only. Measure the duration of up to 50 pending queries and 50 inbox replays; schedule bounded jobs without uncontrolled overlap.
- [ ] Monitor stale reserved/unknown intents. No-checkout cases require merchant evidence and a reviewed recovery procedure, never time-based release or a blind second STK request.
- [ ] Verify service health checks, graceful restart behavior, dependency installation, logs and DB connection errors. Add/use a suitable readiness check that detects DB unavailability without returning secrets; `/api/auth/me` alone is not a database readiness guarantee.
- [ ] Verify no development server/debug mode is used and the process listens on Render's port.
- [ ] After separate authorization, migrate before releasing application code that writes the new tables, then verify backend API health before updating the frontend. Coordinate simultaneous live traffic and migration locks.

## 5. Existing Netlify frontend settings

| Setting | Value when Base Directory is `frontend` |
|---|---|
| Base Directory | `frontend` relative to the actual connected repo root |
| Build command | `npm ci && npm run build` (or the existing equivalent with confirmed dependency installation) |
| Publish directory | `dist` relative to that base |
| Build environment | Correct `VITE_API_URL` for that deploy context; reviewed Node runtime |
| SPA fallback | `/* /index.html 200` in `public/_redirects`; verify copied to `dist/_redirects` |

With a repository-root base, use `npm --prefix frontend ci && npm --prefix frontend run build` and publish `frontend/dist` instead. Do not combine the two path schemes. Netlify's Vite defaults use a build command and `dist` publish output; check the existing site's effective settings. [Netlify Vite guide](https://docs.netlify.com/build/frameworks/framework-setup-guides/vite/).

- [ ] Preview in a separate environment with a matching backend CORS origin; do not loosen production CORS to make previews work.
- [ ] Confirm refreshing `/customer/orders`, `/admin/reports` and `/admin/expenses` serves the SPA rather than a 404.
- [ ] Confirm requests target Render API JSON endpoints, not Netlify's HTML fallback; `VITE_API_URL` must not include a duplicate `/api`.
- [ ] Check HTTPS cookies across actual domains in Chrome, Safari/mobile browsers and privacy-restricted configurations. SameSite=None/Secure does not override every browser third-party-cookie policy. Test any same-site custom-domain/proxy solution before adopting it.

## 6. Staging and authorized release smoke tests

- [ ] Customer login, order placement, cash choice, cancellation, refresh and stock restoration. Verify another customer cannot read/pay/edit the order.
- [ ] Active admin versus anonymous/customer/deactivated-admin permissions on every new route.
- [ ] Product activation/deactivation updates the displayed active product count.
- [ ] Feed and medicine calculations, duplicate submission retries, expense audit trail, edits/deletions and immediate report recalculation.
- [ ] Monday, month/year end, leap day, Nairobi 00:00 boundaries; provider occurrence time versus processing time; empty periods and zero expenses.
- [ ] Reconcile historical paid flags without receipts, missing receipt dates, legacy M-Pesa summaries and legacy refunds dated using `updated_at`. Confirm independent cash receipts are not aggregate totals that already include M-Pesa.
- [ ] Partial/mixed payments, cancelled receipts and recorded refunds produce agreed figures across cash reports and dashboards. Verify the creation-period receivable definition and explicitly cancel non-collectible orders after the refund workflow.
- [ ] Verify unknown receipt/time provenance is visible in operational reconciliation; a successful STK query must not fabricate receipt metadata. Review legacy administrator audit IDs for orphans; retain those identities.
- [ ] Notification counts/read state survive refresh; older pages stay accessible while polling; historical event dates and mobile layouts are correct.
- [ ] Provider sandbox: success/failure/customer cancellation, duplicate/out-of-order/missing callbacks, early callback, timeout and reconciliation recovery. Confirm the actual STK query contract and delivery behavior with Safaricom.
- [ ] A production-provider test requires separate explicit authorization and approved live credentials. Confirm real receipt, amount, timestamp, callback origin/verification and settlement reconciliation before accepting customer payments.

## 7. Rollback and monitoring

- [ ] Watch verification failures, pending-attempt age, ambiguous initiation outcomes, duplicate-receipt conflicts, mismatched totals, reconciliation alerts, 5xx responses, database locks, worker timeouts and auth errors.
- [ ] Keep credentials and callback personal details out of logs; verify logging configuration in the hosting environment.
- [ ] Preserve the prior backend/frontend releases for code rollback; avoid reverting any payment/audit data. Suspend new payments if correctness is uncertain and preserve receipts for reconciliation.
- [ ] Reconcile provider transactions during and after the deployment window. Resume normal operation only after the release owner approves the verified results.

## 8. Backup restoration and rollback rehearsal

- [ ] Before any authorized production migration, take a consistent PostgreSQL backup using the existing Render recovery facility or `pg_dump` on the explicitly verified database. Store it encrypted/access-controlled with retention, timestamp and PostgreSQL/tool versions recorded. Do not write credentials into shell history or logs.
- [ ] Restore to a separate empty staging database using the matching PostgreSQL tools. Confirm tables, constraints, row fingerprints, receipt totals and admin/customer login. A backup is not verified until its restoration is tested.
- [ ] Rehearse the migration twice on that restored copy and compare complete original business rows. Rehearse an injected DDL failure only in the isolated test schema and verify rollback. Do not rewrite historical payment rows to make validation pass.
- [ ] Keep the previous code release, but preserve all additive safety/audit tables and financial records during rollback. Stop new payment initiation if old code cannot safely understand unresolved new intents. Do not blindly roll back to the known payment-unsafe implementation.
- [ ] Database restoration is an incident operation that can lose intervening payments/orders. Require a separate approval, a recovery point, provider reconciliation and a plan to retain/replay legitimate writes before replacing any live database.
