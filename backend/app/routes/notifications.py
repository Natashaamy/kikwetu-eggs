"""Persistent admin event inbox with per-administrator read state."""
from flask import Blueprint, jsonify, request, session
from ..auth import admin_required
from ..db import get_db

notifications_bp = Blueprint('notifications', __name__, url_prefix='/api/admin/notifications')


def notify(db, key, title, description, order_id=None, created_at=None):
    db.execute("""INSERT INTO admin_notifications(event_key,title,description,order_id,created_at)
        VALUES (?,?,?,?,COALESCE(?,CURRENT_TIMESTAMP)) ON CONFLICT(event_key) DO NOTHING""", (key, title, description, order_id, created_at))


@notifications_bp.before_request
@admin_required
def protect():
    return None


@notifications_bp.get('')
def inbox():
    db = get_db()
    try:
        before = int(request.args.get('before', '9223372036854775807'))
    except ValueError:
        return jsonify(error='Invalid notification cursor'), 400
    if before < 1 or before > 9223372036854775807:
        return jsonify(error='Invalid notification cursor'), 400
    # Reconcile durable events on refresh as well as immediate write hooks.
    # Unique event keys make polling and retries idempotent.
    for row in db.execute('SELECT order_id,order_number,total_amount,order_status,created_at,updated_at FROM orders').fetchall():
        notify(db, f"order:{row['order_id']}", 'New Order Received', f"{row['order_number']} worth KES {row['total_amount']}", row['order_id'], row['created_at'])
        if row['order_status'] == 'cancelled':
            notify(db, f"cancel:{row['order_id']}", 'Order Cancelled', row['order_number'], row['order_id'], row['updated_at'])
    for row in db.execute("SELECT transaction_id,order_id,status,completed_at FROM mpesa_transactions WHERE status != 'pending'").fetchall():
        notify(db, f"payment:{row['transaction_id']}:{row['status']}", 'M-Pesa Payment ' + row['status'].title(), f"Order #{row['order_id']}: {row['status']}", row['order_id'], row['completed_at'])
    for row in db.execute('SELECT product_id,name,updated_at,stock_quantity FROM products WHERE is_active AND stock_quantity <= low_stock_threshold').fetchall():
        notify(db, f"stock:{row['product_id']}:{row['updated_at']}", 'Low Product Stock', f"{row['name']}: {row['stock_quantity']} units remaining", created_at=row['updated_at'])
    cursor_condition, cursor_args = '1=1', []
    if before != 9223372036854775807:
        anchor = db.execute('SELECT created_at FROM admin_notifications WHERE id = ?', (before,)).fetchone()
        if anchor is None:
            db.rollback()
            return jsonify(error='Invalid notification cursor'), 400
        cursor_condition = '(n.created_at < ? OR (n.created_at = ? AND n.id < ?))'
        cursor_args = [anchor['created_at'], anchor['created_at'], before]
    rows = db.execute(f"""SELECT n.*, r.read_at FROM admin_notifications n
        LEFT JOIN notification_reads r ON r.notification_id = n.id AND r.admin_id = ?
        WHERE {cursor_condition} ORDER BY n.created_at DESC, n.id DESC LIMIT 30""", [session['user_id'], *cursor_args]).fetchall()
    count = db.execute("""SELECT COUNT(*) AS count FROM admin_notifications n WHERE NOT EXISTS
        (SELECT 1 FROM notification_reads r WHERE r.notification_id = n.id AND r.admin_id = ?)""", (session['user_id'],)).fetchone()['count']
    db.commit()
    return jsonify(notifications=[dict(r) for r in rows], unread_count=count, next_cursor=rows[-1]['id'] if len(rows) == 30 else None)


@notifications_bp.patch('/<int:notification_id>/read')
def mark_read(notification_id):
    db = get_db()
    if db.execute('SELECT id FROM admin_notifications WHERE id = ?', (notification_id,)).fetchone() is None:
        return jsonify(error='Notification not found'), 404
    db.execute('INSERT INTO notification_reads(notification_id, admin_id) VALUES (?,?) ON CONFLICT DO NOTHING', (notification_id, session['user_id']))
    db.commit()
    return jsonify(message='Notification read')


@notifications_bp.patch('/read-all')
def read_all():
    db = get_db()
    db.execute('''INSERT INTO notification_reads(notification_id, admin_id)
        SELECT id, ? FROM admin_notifications WHERE 1=1 ON CONFLICT DO NOTHING''', (session['user_id'],))
    db.commit()
    return jsonify(message='All notifications read')
