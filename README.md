# Kikwetu Eggs

Kikwetu Eggs is a React and Flask ordering, inventory, payment, and sales
management system. PostgreSQL is used in deployment. SQLite remains available
as a convenient local-development fallback.

## Project areas

- `frontend/` — React and Vite user interface.
- `backend/` — Flask API, database schemas, initialization, and tests.
- `docs/` — Project documentation and design notes.

## Local backend setup

From `backend/`, create and activate a virtual environment, then install the
dependencies:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

When `DATABASE_URL` is absent, Flask uses the local database at
`backend/instance/chicken_business.db`. Initialize any missing local tables:

```powershell
python init_db.py
flask --app app run --debug
```

`schema_sqlite.sql` exists only for this local fallback. The deployment schema
is `schema.sql`, which uses PostgreSQL types and constraints.

To develop locally against PostgreSQL instead, set a connection URL before
initializing and starting Flask:

```powershell
$env:DATABASE_URL = "postgresql://USER:PASSWORD@HOST:5432/DATABASE"
python init_db.py
flask --app app run --debug
```

## Render deployment

For the existing Render/Netlify deployment, follow [the deployment checklist](docs/deployment-checklist.md) and [current readiness audit](docs/production-readiness-audit.md). Reuse the existing services and database. The Git root here contains `backend/` and `frontend/`; the local parent folder name is not a repository subdirectory. The commands below assume the Render root is the Git root.

Use this build command:

```text
pip install -r backend/requirements.txt
```

Use this start command:

```text
cd backend && gunicorn --bind 0.0.0.0:$PORT "app:create_app()"
```

Run `python migrate_financial_admin.py` from `backend` as a separately reviewed release step after backup and PostgreSQL staging verification. Do not run the initializer on every service start: it also supports administrator bootstrap/password reset. Confirm older customer-account migrations were already applied; schema validation fails if a required structure is missing. See the checklist for recovery and rollback.

Required Render variables:

- `APP_ENV=production` — fail startup when required production configuration is absent.
- `DATABASE_URL` — supplied by the linked Render PostgreSQL database.
- `SECRET_KEY` — a long random value used to sign Flask sessions.
- `FRONTEND_URL=https://YOUR-NETLIFY-SITE.netlify.app` — the exact Netlify
  origin permitted to make credentialed API requests (no trailing slash).
- `FLASK_HTTPS=1` — enables secure session cookies behind Render HTTPS.

The backend permits credentialed cross-origin requests only from
`FRONTEND_URL` and only for `/api/*`. In production, `FLASK_HTTPS=1` changes
the session cookie to `Secure`, `HttpOnly`, and `SameSite=None`, allowing the
Netlify frontend to send it to the HTTPS Render API. Local HTTP development
defaults to `http://localhost:5173` with `SameSite=Lax` and a non-secure cookie;
these local defaults must not be used for the deployed service.

Authentication POST requests are rate limited per client IP: login permits
10 attempts per minute and 30 per hour, while registration permits 3 attempts
per minute and 10 per hour. Login also permits only 5 attempts per minute and
20 per hour for each submitted login identifier, independently of its client
IP. Identifiers use the same whitespace and case normalization as login and
are stored in limiter keys only as SHA-256 digests. In production, the limiter reads Render's
documented real-client value from the first `X-Forwarded-For` entry, accepts it
only when it is a valid IPv4 or IPv6 address, and otherwise falls back to the
direct connection address. Local HTTP development never trusts forwarded-IP
headers. Limits use in-process memory, require no new environment variable,
reset whenever the service restarts, and are not shared between multiple
backend instances. Move to a shared limiter store before running more than one
instance.

M-Pesa variables (keep sandbox until merchant/infrastructure verification passes):

- `MPESA_ENV=sandbox` (`production` requires separate release approval)
- `MPESA_TRANSACTION_TYPE=CustomerPayBillOnline` (or the verified merchant BuyGoods type)
- `MPESA_CONSUMER_KEY`
- `MPESA_CONSUMER_SECRET`
- `MPESA_SHORTCODE`
- `MPESA_PASSKEY`
- `MPESA_CALLBACK_URL`

### Creating the initial administrator

Set all four variables before the first deployment:

- `INITIAL_ADMIN_NAME`
- `INITIAL_ADMIN_USERNAME`
- `INITIAL_ADMIN_EMAIL`
- `INITIAL_ADMIN_PASSWORD`

During startup, `init_db.py` hashes the password with Werkzeug and inserts the
administrator only when no administrator with that username or email exists.
The password is never printed or stored as plain text. After the account exists,
the four initial-admin variables can be removed from Render.

### Temporarily resetting an administrator password

If an existing administrator's password is lost and Render Shell is not
available, temporarily set both of these Render environment variables:

- `RESET_ADMIN_USERNAME` — the existing administrator username.
- `RESET_ADMIN_PASSWORD` — the new plain-text password, supplied only through
  Render's protected environment settings.

During a separately authorized one-time recovery run, `init_db.py` normalizes the username, finds
that administrator, hashes the new password with Werkzeug, and updates only the
matching administrator's `password_hash`. It does not create an account when
the username is unknown and never prints the password or hash. Wait for the
safe `Admin password reset completed.` log message, verify login, and then
remove both recovery variables immediately. Leaving them configured would
reset the password again whenever the initializer is run.

## Local frontend

```powershell
cd frontend
npm install
npm run dev
```

Set `VITE_API_URL=http://127.0.0.1:5000` for local development. The API helper uses that origin; no Vite development proxy is configured. Netlify requires the existing backend HTTPS origin at build time (without `/api`). Production builds reject HTTP, localhost, URL credentials, paths and secret-like `VITE_*` variable names. Set the real HTTPS backend origin before running `npm run build`.

`netlify.toml` sets base `frontend`, build `npm run build`, publish `dist`, Node 24 and the SPA fallback. Confirm the existing site's branch/context settings separately; this file does not select the production branch. See [the staging handoff](docs/github-deployment-handoff.md) for current verification and remaining hosting gates.

## Tests

Run backend tests from `backend/`:

```powershell
python -m unittest discover -s tests -v
```

## Payment recovery and staging verification

Run `python reconcile_payments.py` from `backend` only against the approved environment. Schedule bounded batches and monitor unresolved intents; never retry an unknown payment solely because time elapsed.

Five PostgreSQL integration tests are opt-in. Configure `PGTEST_DATABASE_URL` securely for an isolated database and set `PGTEST_CONFIRM_ISOLATED=1`; never point these at production. See [the safety correction report](docs/production-safety-corrections.md) for verified results and release gates.
