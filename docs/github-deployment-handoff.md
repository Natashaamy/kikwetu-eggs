# GitHub and hosting handoff — 9 November 2026

## Branch and release safety

Repository: `https://github.com/Natashaamy/kikwetu-eggs.git` (`origin`).
Initial local branch: `main`; remote `main` was verified at
`b6d6a577ae206212edb2a7911aef9261985dc0a0` before preparing this release.
Release branch: `staging/deployment-readiness-2026-11-09`.

Payment, schema and authentication changes require staging verification. Do not
merge this branch into a monitored production branch or trigger production
deployment until the gates in `production-safety-corrections.md` are satisfied.
Neither provider's monitored branch is confirmed. No hosting credentials or
site linkage are available locally, and no Render blueprint exists. Do not
infer hosting branch settings from the repository's `main` branch.

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

Outstanding: identify site/service URLs and monitored branches; provision or
identify separate staging services/database; configure matching staging URL,
CORS and sandbox callback; run skipped PostgreSQL tests and migration rehearsal;
verify Linux startup, actual browser authentication/protected routes, console,
backend logs, database and sandbox order/payment workflows. Netlify and Render
deployment success cannot be claimed until those checks are observed.
