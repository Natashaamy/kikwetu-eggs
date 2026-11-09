"""Run a bounded recovery batch on the explicitly configured application database.

Schedule every minute in staging/production after release authorization.
Queries existing checkouts only; never initiates a payment or refund.
"""
from app import create_app
from app.db import get_db
from app.services.payment_reconciliation import reconcile_pending

if __name__ == '__main__':
    with create_app().app_context():
        results = reconcile_pending(get_db())
        print(f'Reconciliation batch: {len(results)} operations; '
              f'{sum(status == 200 for _, status in results)} completed.')
