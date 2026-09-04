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

Create a Render PostgreSQL database and a Python web service for this repository.
Link the database to the web service so Render supplies `DATABASE_URL`. Set the
service root directory to `ChickenBusinesssystem` when the repository contains
the parent workspace folders shown here.

Use this build command:

```text
pip install -r backend/requirements.txt
```

Use this start command:

```text
cd backend && python init_db.py && gunicorn --bind 0.0.0.0:$PORT "app:create_app()"
```

Running `init_db.py` on every service start is safe: it uses
`CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`. It never drops
tables and never seeds fake business data.

The initializer also performs a small idempotent customer-account migration.
On PostgreSQL it runs `ALTER TABLE customers ADD COLUMN IF NOT EXISTS` for the
`is_active` flag. On SQLite it first checks `PRAGMA table_info(customers)` and
adds the column only when missing. Existing customers receive the active
default, and no customer or business-history rows are recreated or deleted.

Required Render variables:

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

M-Pesa sandbox variables, when payment testing is enabled:

- `MPESA_ENV=sandbox`
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

On the next deployment or restart, `init_db.py` normalizes the username, finds
that administrator, hashes the new password with Werkzeug, and updates only the
matching administrator's `password_hash`. It does not create an account when
the username is unknown and never prints the password or hash. Wait for the
safe `Admin password reset completed.` log message, verify login, and then
remove both recovery variables immediately. Leaving them configured would
reset the password again on every service start.

## Local frontend

```powershell
cd frontend
npm install
npm run dev
```

The Vite development proxy forwards `/api` requests to the local Flask server.

## Tests

Run backend tests from `backend/`:

```powershell
python -m unittest discover -s tests -v
```
