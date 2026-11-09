# GitHub and hosting handoff — 9 November 2026

## Branch and release safety

Repository: `https://github.com/Natashaamy/kikwetu-eggs.git` (`origin`).
Initial local branch: `main`; remote `main` was verified at
`b6d6a577ae206212edb2a7911aef9261985dc0a0` before preparing this release.
Release branch: `staging/deployment-readiness-2026-11-09`.

Payment, schema and authentication changes require staging verification. Do not
merge this branch into a monitored production branch or trigger production
deployment until the gates in `production-safety-corrections.md` are satisfied.
The user confirmed Netlify monitors `main`; Render screenshots confirm `main`,
Auto-Deploy On Commit, root `backend`, build `pip install -r requirements.txt`,
and current start `python init_db.py && gunicorn --bind 0.0.0.0:$PORT "app:create_app()"`.
The pre-deploy command is empty. No hosting setting has been changed.

## Verification performed

- Backend: `python -m unittest discover -s tests -v` from `backend`, using
  `.test-venv`: 124 discovered, 119 passed, 5 PostgreSQL integration tests skipped.
- Browser: `npm run test`: all 10 Playwright Chrome tests passed. These use
  mocked API responses; they do not verify deployed cookies, database or Daraja.
- Production frontend build passed with an explicit non-live HTTPS test origin,
  `https://api.staging.example.invalid`. This tests compilation only; generated
  output is ignored and must not be deployed. The actual Render origin is unknown.
- The build correctly rejects `http://localhost:5000`. `dist/_redirects` contains
  the SPA fallback. No local backend URL was found in the HTTPS test build.
- `npm ls --all` succeeded; package manifest dependencies match the lockfile.
  Python `pip check` passed. Prior npm advisory findings remain documented in
  `production-readiness-npm-audit.json`; no clean security audit is claimed.
- `git diff --check` passed. Environment files, virtual environments, databases,
  build output and test output are ignored. Only `.env.example` files belong
  in Git. Existing readiness JSON files are historical local evidence.

## Existing hosting configuration to verify

Netlify: retain the existing site. Repository `netlify.toml` sets base
`frontend`, build `npm run build`, publish `dist`, Node 24 and SPA fallback.
Netlify installs dependencies before building; development dependencies are
required. Set build-context `VITE_API_URL` to the actual HTTPS Render origin,
without `/api`. Give staging its own backend origin. Never expose backend
credentials through `VITE_*`. Production builds now validate the API URL and
reject secret-like exposed variable names. The ignored local frontend `.env`
is for development and must be overridden for a production build.

Render: retain the existing service and PostgreSQL database. For repository-root
service settings, build `pip install -r backend/requirements.txt` and start
`cd backend && gunicorn --bind 0.0.0.0:$PORT "app:create_app()"`.
With root directory `backend`, omit those directory prefixes. Windows checks
verify the Flask factory through tests; Linux Gunicorn startup, logs and actual
PostgreSQL connectivity have not been verified.

Required Render configuration: `APP_ENV=production`, protected `DATABASE_URL`,
stable protected `SECRET_KEY`, `FLASK_HTTPS=1`, and `FRONTEND_URL` equal to the
actual frontend HTTPS origin. CORS permits this origin with credentials;
frontend requests include credentials. Secure, HttpOnly, SameSite=None session
cookies are configured for HTTPS, but cross-site browser policies still require
tests on the actual domains. Do not add wildcard origins for previews.

Keep `MPESA_ENV=sandbox` for staging. Set protected `MPESA_CONSUMER_KEY`,
`MPESA_CONSUMER_SECRET`, `MPESA_SHORTCODE`, `MPESA_PASSKEY`, verified
`MPESA_TRANSACTION_TYPE`, and public HTTPS `MPESA_CALLBACK_URL` ending
`/api/payments/mpesa/callback`. Provider callback reachability is unverified.
Leave admin bootstrap/recovery variables unset for routine deployment.

## Migration and deployment status

No production migration, real payment, hosting settings change or deployment
was performed. The reviewed additive migration is
`cd backend && python migrate_financial_admin.py`, with the intended database
securely injected. It requires backup/restore rehearsal, isolated PostgreSQL
verification and separate production authorization. Do not run `init_db.py`
on service startup. Schedule bounded reconciliation only in the approved
environment; see the deployment checklist.

## Subsequent isolated staging work

A portable PostgreSQL 17.11 server was obtained from EDB's official binary
distribution, unpacked under ignored `.staging-local`, and bound only to
`127.0.0.1:55439` with a randomly generated local SCRAM password. No production
connection string or data was used. This is local verification, not a hosted
Render staging deployment or a claim about the unknown production major version.

All five originally skipped PostgreSQL tests passed. Five further PostgreSQL
tests passed for partial payments, idempotency, missed-callback recovery,
callback-outage recovery and receipt conflicts. These provider responses are
mocked. A further constraint test checks negative amounts, missing order FKs
and the unique active-payment-attempt index.

Final combined run: **134 backend tests passed, zero skips**, including all
11 PostgreSQL tests. The disposable server was stopped after verification;
its runtime, credentials, data and backup remain ignored by Git.

A separate synthetic legacy-only database was migrated twice; complete row
fingerprints of seven business tables were unchanged. A custom-format
`pg_dump` backup was restored with `pg_restore --exit-on-error` into another
new local database; fingerprints and sequence state matched. Restored schema
validation and an authenticated financial-report request passed. Flask factory
startup did not invoke `init_db.py`; Linux/Gunicorn startup remains unverified.
These local rehearsals do not establish that a production backup can be restored.

`APP_ENV=staging` now enforces hosted secret/database/HTTPS requirements and
rejects `MPESA_ENV=production`, both at factory startup and in the provider
client (including reconciliation workers). Four focused staging-configuration
tests pass. Set `APP_ENV=staging`, `MPESA_ENV=sandbox` on future staging services.
Resource isolation still requires an independently created database and explicit
verification of its host/database/role before injecting `DATABASE_URL`; the
application cannot infer database ownership from a connection string.

The frontend's ten browser tests and HTTPS-origin production compilation passed
again. The browser tests mock the API and the compilation uses an invalid test
origin; neither verifies an actual deployed service. In-app notifications write
only to the configured database inbox; no external customer messaging sender was
found in this notification path.

Outstanding: Chrome access approval timed out and browser access is unavailable;
the Render plugin is not installed/connected. No hosted staging resource was
created and no costs incurred. Hosted staging, matching CORS/cookies, actual
sandbox credentials/test phone/public callback, provider behavior, Linux startup,
backend logs and real frontend/backend workflows remain blocked by access and
configuration. No actual Daraja request was sent. Credentials must be supplied
through protected staging settings, never Git or chat.

After those gates pass, obtain explicit production release approval. Preserve
the current release IDs, verify a restorable production backup, and obtain
separate authorization to run `python migrate_financial_admin.py` from `backend`
against the verified production target. Validate the schema before application
traffic uses it. Coordinate the existing main-triggered deployments so the
backend is healthy before publishing the frontend. The final Render start
command should omit `init_db.py`, but changing production settings is still
unapproved. Run the full suite with isolated PostgreSQL enabled, verify the
latest remote main is still an ancestor, then use a fast-forward-only merge.

Rollback: retain additive tables and financial/audit records; suspend new payment
initiation if needed, preserve callbacks and unresolved attempts, and use a
reviewed compatible prior release. Do not blindly roll back to the known older
payment behavior. Database restoration requires separate incident approval and
provider reconciliation because it can discard legitimate intervening writes.
