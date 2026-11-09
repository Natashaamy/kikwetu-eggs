"""Auditable, idempotent farm expense administration."""
import json
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from flask import Blueprint, jsonify, request, session
from ..auth import admin_required
from ..db import get_db
from ..business_time import period_dates, utc_now, NAIROBI

expenses_bp = Blueprint("expenses", __name__, url_prefix="/api/admin/expenses")


@expenses_bp.before_request
@admin_required
def protect():
    return None


def validate(data):
    if not isinstance(data, dict):
        raise ValueError("A JSON expense is required")
    category = data.get("category")
    if category not in ("feed", "medicine"):
        raise ValueError("Choose feed or medicine")
    values = {}
    for field, limit in (("item_name", 150), ("unit", 40), ("notes", 2000)):
        value = data.get(field, "")
        if not isinstance(value, str) or len(value.strip()) > limit or (field != "notes" and not value.strip()):
            raise ValueError(f"Invalid {field.replace('_', ' ')}")
        values[field] = value.strip()
    try:
        quantity, price = Decimal(str(data.get("quantity"))), Decimal(str(data.get("unit_price")))
        if not quantity.is_finite() or not price.is_finite() or not 0 < quantity <= 1000000 or not 0 <= price <= 100000000:
            raise ValueError("Quantity must be positive and price non-negative, within supported limits")
        if quantity != quantity.quantize(Decimal(".001")) or price != price.quantize(Decimal(".01")):
            raise ValueError("Use at most three quantity decimals and two price decimals")
        purchased = date.fromisoformat(data.get("purchase_date", ""))
    except (InvalidOperation, TypeError):
        raise ValueError("Enter valid quantities, prices and a purchase date")
    if purchased > utc_now().astimezone(NAIROBI).date():
        raise ValueError("Purchase date cannot be in the future")
    if quantity * price > Decimal('9999999999.99'):
        raise ValueError("Expense total exceeds the supported amount")
    return {"category": category, **values, "unit": "kg" if category == "feed" else values["unit"],
            "quantity": str(quantity), "unit_price": str(price),
            "total_amount": str((quantity * price).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)),
            "purchase_date": purchased.isoformat()}


def expense_totals(database, start, end):
    totals = {"feed": Decimal(0), "medicine": Decimal(0)}
    for row in database.execute("SELECT category, total_amount FROM farm_expenses WHERE deleted_at IS NULL AND purchase_date >= ? AND purchase_date <= ?", (str(start), str(end))).fetchall():
        totals[row["category"]] += Decimal(str(row["total_amount"]))
    return {**{k: str(v.quantize(Decimal('.01'))) for k, v in totals.items()}, "total": str(sum(totals.values()).quantize(Decimal('.01')))}


@expenses_bp.get("")
def list_expenses():
    db = get_db()
    conditions, args = ["deleted_at IS NULL"], []
    try:
        for key, operator in (("from", ">="), ("to", "<=")):
            if request.args.get(key):
                value = date.fromisoformat(request.args[key]).isoformat()
                conditions.append(f"purchase_date {operator} ?")
                args.append(value)
        if request.args.get("from") and request.args.get("to") and request.args['from'] > request.args['to']:
            raise ValueError("Invalid date range")
        if request.args.get("category"):
            if request.args['category'] not in ('feed', 'medicine'):
                raise ValueError("Invalid category")
            conditions.append("category = ?")
            args.append(request.args['category'])
        rows = db.execute("SELECT * FROM farm_expenses WHERE " + " AND ".join(conditions) + " ORDER BY purchase_date DESC, id DESC", args).fetchall()
        return jsonify(expenses=[dict(r) for r in rows], week=expense_totals(db, *period_dates('week')), month=expense_totals(db, *period_dates('month')))
    except ValueError as error:
        return jsonify(error=str(error)), 400


def audit(db, expense_id, action, snapshot):
    db.execute("INSERT INTO expense_audit(expense_id, action, snapshot, changed_by) VALUES (?, ?, ?, ?)",
               (expense_id, action, json.dumps(snapshot, default=str, sort_keys=True), session['user_id']))


@expenses_bp.post("")
def add_expense():
    db = get_db()
    try:
        data = request.get_json(silent=True)
        values = validate(data)
        key = data.get('submission_key')
        if not isinstance(key, str) or not 16 <= len(key) <= 100:
            raise ValueError("A valid submission key is required")
        fingerprint = json.dumps(values, sort_keys=True)
        db.begin()
        row = db.execute("""INSERT INTO farm_expenses(category,item_name,unit,notes,quantity,unit_price,total_amount,purchase_date,created_by,submission_key,submission_payload)
            VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(submission_key) DO NOTHING RETURNING id""",
            (values['category'], values['item_name'], values['unit'], values['notes'],
             values['quantity'], values['unit_price'], values['total_amount'], values['purchase_date'],
             session['user_id'], key, fingerprint)).fetchone()
        if row is None:
            existing = db.execute("SELECT id, submission_payload FROM farm_expenses WHERE submission_key = ?", (key,)).fetchone()
            db.rollback()
            if existing['submission_payload'] != fingerprint:
                return jsonify(error="Submission key already used for another expense"), 409
            return jsonify(id=existing['id'], message="Expense already saved"), 200
        audit(db, row['id'], 'create', values)
        db.commit()
        return jsonify(id=row['id'], message="Expense saved successfully"), 201
    except ValueError as error:
        db.rollback()
        return jsonify(error=str(error)), 400


@expenses_bp.put('/<int:expense_id>')
@expenses_bp.patch('/<int:expense_id>')
@expenses_bp.delete('/<int:expense_id>')
def change_expense(expense_id):
    db = get_db()
    try:
        values = validate(request.get_json(silent=True)) if request.method != 'DELETE' else None
        db.begin()
        row = db.execute("SELECT * FROM farm_expenses WHERE id = ? AND deleted_at IS NULL" + (" FOR UPDATE" if db.postgres else ""), (expense_id,)).fetchone()
        if row is None:
            db.rollback()
            return jsonify(error="Expense not found"), 404
        audit(db, expense_id, 'delete' if values is None else 'edit', dict(row))
        if values is None:
            db.execute("UPDATE farm_expenses SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (expense_id,))
        else:
            db.execute("UPDATE farm_expenses SET " + ', '.join(f'{key} = ?' for key in values) + ", updated_at = CURRENT_TIMESTAMP WHERE id = ?", (*values.values(), expense_id))
        db.commit()
        return jsonify(message="Expense deleted" if values is None else "Expense updated successfully")
    except ValueError as error:
        db.rollback()
        return jsonify(error=str(error)), 400
