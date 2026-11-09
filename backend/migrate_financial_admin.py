"""Validate and atomically install frozen additive migrations. Never rewrite business rows."""
import hashlib
from app import create_app
from app.db import get_db
from app.schema_validation import validate, scripts, SchemaMismatch


def migrate(app):
    with app.app_context():
        db=get_db()
        try:
            db.begin()
            if db.postgres:
                db.execute("SET LOCAL lock_timeout = '5s'")
                db.execute("SET LOCAL statement_timeout = '60s'")
                db.execute('SELECT pg_advisory_xact_lock(624731912)')
            validate(db,allow_missing_new=True,allow_missing_indexes=True)
            stamp='TIMESTAMPTZ' if db.postgres else 'TEXT'
            db.execute(f"CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at {stamp} NOT NULL DEFAULT CURRENT_TIMESTAMP)")
            for version,sql in scripts(db.postgres)[1:]:
                checksum=hashlib.sha256(sql.encode()).hexdigest()
                old=db.execute('SELECT checksum FROM schema_migrations WHERE version=?',(version,)).fetchone()
                if old and old['checksum'] != checksum:
                    raise SchemaMismatch(f'Migration checksum changed: {version}')
                # execute statements within our transaction; SQLite executescript would commit it.
                for statement in sql.split(';'):
                    if statement.strip():
                        db.execute(statement)
                if not old:
                    db.execute('INSERT INTO schema_migrations(version,checksum) VALUES (?,?)',(version,checksum))
            validate(db)
            db.commit()
        except Exception:
            db.rollback()
            raise


if __name__=='__main__':
    migrate(create_app())
    print('Schema validated; additive migrations applied without rewriting existing business records.')
