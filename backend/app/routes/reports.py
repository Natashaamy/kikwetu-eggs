"""Admin-only business reports and CSV export."""

import csv
from datetime import date
from io import StringIO
import sqlite3

from flask import Blueprint, Response, jsonify, request

from ..auth import admin_required
from ..db import get_db


reports_bp = Blueprint("reports", __name__, url_prefix="/api/admin/reports")


@reports_bp.before_request
@admin_required
def protect_reports():
    return None


def report_period():
    """Validate and return optional inclusive ISO date filters."""
    from_date = request.args.get("from") or None
    to_date = request.args.get("to") or None

    try:
        if from_date:
            date.fromisoformat(from_date)
        if to_date:
            date.fromisoformat(to_date)
    except ValueError as error:
        raise ValueError("Dates must use YYYY-MM-DD format") from error

    if from_date and to_date and from_date > to_date:
        raise ValueError("From date cannot be after to date")

    return from_date, to_date


def date_filter(alias="orders"):
    """Build a parameterized, inclusive date condition."""
    from_date, to_date = report_period()
    conditions = []
    parameters = []
    if from_date:
        conditions.append(f"date({alias}.created_at) >= date(?)")
        parameters.append(from_date)
    if to_date:
        conditions.append(f"date({alias}.created_at) <= date(?)")
        parameters.append(to_date)
    return (" AND ".join(conditions) or "1 = 1"), parameters, from_date, to_date


@reports_bp.get("")
def get_report():
    """Calculate all report sections from current database records."""
    database = get_db()

    try:
        period_sql, parameters, from_date, to_date = date_filter()

        summary = database.execute(
            f"""
            SELECT
                COUNT(*) AS total_orders,
                COALESCE(SUM(CASE WHEN order_status = 'pending' THEN 1 ELSE 0 END), 0)
                    AS pending_orders,
                COALESCE(SUM(CASE WHEN order_status = 'processing' THEN 1 ELSE 0 END), 0)
                    AS processing_orders,
                COALESCE(SUM(CASE WHEN order_status = 'completed' THEN 1 ELSE 0 END), 0)
                    AS completed_orders,
                COALESCE(SUM(CASE WHEN order_status = 'cancelled' THEN 1 ELSE 0 END), 0)
                    AS cancelled_orders,
                COALESCE(SUM(CASE WHEN order_status = 'completed'
                    THEN total_amount ELSE 0 END), 0) AS completed_revenue,
                COALESCE(AVG(CASE WHEN order_status = 'completed'
                    THEN total_amount END), 0) AS average_completed_order,
                COALESCE(SUM(CASE WHEN payment_status = 'paid' THEN 1 ELSE 0 END), 0)
                    AS paid_orders,
                COALESCE(SUM(CASE WHEN payment_status = 'unpaid' AND order_status != 'cancelled' THEN 1 ELSE 0 END), 0)
                    AS unpaid_orders,
                COALESCE(SUM(CASE WHEN payment_status = 'paid' THEN total_amount ELSE 0 END), 0)
                    AS payments_received,
                COALESCE(SUM(CASE WHEN payment_status = 'unpaid' AND order_status != 'cancelled' THEN total_amount ELSE 0 END), 0)
                    AS outstanding_amount
            FROM orders
            WHERE {period_sql}
            """,
            parameters,
        ).fetchone()

        top_products = database.execute(
            f"""
            SELECT
                products.product_id,
                products.name,
                products.unit_name,
                products.stock_quantity,
                SUM(order_items.quantity) AS units_sold,
                COUNT(DISTINCT orders.order_id) AS completed_orders,
                SUM(order_items.line_total) AS revenue
            FROM order_items
            JOIN orders ON orders.order_id = order_items.order_id
            JOIN products ON products.product_id = order_items.product_id
            WHERE orders.order_status = 'completed' AND {period_sql}
            GROUP BY products.product_id
            ORDER BY units_sold DESC, revenue DESC, products.name
            LIMIT ?
            """,
            [*parameters, 10],
        ).fetchall()

        top_customers = database.execute(
            f"""
            SELECT
                customers.customer_id,
                customers.name,
                customers.phone_number,
                COUNT(orders.order_id) AS completed_orders,
                SUM(orders.total_amount) AS total_spent,
                MAX(orders.created_at) AS last_completed_order
            FROM orders
            JOIN customers ON customers.customer_id = orders.customer_id
            WHERE orders.order_status = 'completed' AND {period_sql}
            GROUP BY customers.customer_id
            ORDER BY total_spent DESC, completed_orders DESC, customers.name
            LIMIT ?
            """,
            [*parameters, 10],
        ).fetchall()

        recent_completed_orders = database.execute(
            f"""
            SELECT
                orders.order_id,
                orders.order_number,
                customers.name AS customer_name,
                orders.total_amount,
                orders.updated_at AS completed_date,
                orders.created_at
            FROM orders
            JOIN customers ON customers.customer_id = orders.customer_id
            WHERE orders.order_status = 'completed' AND {period_sql}
            ORDER BY orders.updated_at DESC, orders.order_id DESC
            LIMIT ?
            """,
            [*parameters, 10],
        ).fetchall()

        payment_methods = database.execute(
            f"""SELECT payment_method, COUNT(*) AS paid_orders,
                       COALESCE(SUM(total_amount), 0) AS amount
                FROM orders
                WHERE payment_status = 'paid' AND {period_sql}
                GROUP BY payment_method
                ORDER BY amount DESC""",
            parameters,
        ).fetchall()

        sales_over_time = database.execute(
            f"""SELECT date(created_at) AS sale_date, COUNT(*) AS orders,
                       COALESCE(SUM(total_amount), 0) AS revenue
                FROM orders
                WHERE order_status = 'completed' AND {period_sql}
                GROUP BY date(created_at)
                ORDER BY sale_date""",
            parameters,
        ).fetchall()

        recent_orders = database.execute(
            f"""SELECT orders.order_number, customers.name AS customer_name,
                       orders.created_at, orders.total_amount, orders.order_status,
                       orders.payment_status, orders.payment_method
                FROM orders
                JOIN customers ON customers.customer_id = orders.customer_id
                WHERE {period_sql}
                ORDER BY orders.created_at DESC, orders.order_id DESC
                LIMIT ?""",
            [*parameters, 20],
        ).fetchall()

        return jsonify({
            "period": {"from": from_date, "to": to_date},
            "summary": dict(summary),
            "top_products": [dict(row) for row in top_products],
            "top_customers": [dict(row) for row in top_customers],
            "recent_completed_orders": [dict(row) for row in recent_completed_orders],
            "payment_methods": [dict(row) for row in payment_methods],
            "sales_over_time": [dict(row) for row in sales_over_time],
            "recent_orders": [dict(row) for row in recent_orders],
        }), 200
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except sqlite3.Error:
        return jsonify({"error": "Report data could not be loaded"}), 500


def csv_safe(value):
    """Prevent spreadsheet software from interpreting exported text as formulas."""
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(("=", "+", "-", "@")) else text


@reports_bp.get("/export.csv")
def export_report_csv():
    """Export completed order lines for the selected report period."""
    database = get_db()

    try:
        period_sql, parameters, from_date, to_date = date_filter()
        rows = database.execute(
            f"""
            SELECT
                orders.order_number,
                customers.name AS customer_name,
                customers.phone_number,
                products.name AS product_name,
                order_items.quantity,
                order_items.unit_price,
                order_items.line_total,
                orders.total_amount AS order_total,
                orders.order_status,
                orders.payment_status,
                orders.payment_method,
                orders.paid_at,
                orders.created_at AS order_date
            FROM orders
            JOIN customers ON customers.customer_id = orders.customer_id
            JOIN order_items ON order_items.order_id = orders.order_id
            JOIN products ON products.product_id = order_items.product_id
            WHERE orders.order_status = 'completed' AND {period_sql}
            ORDER BY orders.created_at DESC, orders.order_id DESC,
                     order_items.order_item_id
            """,
            parameters,
        ).fetchall()

        output = StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow([
            "Order Number", "Customer", "Phone", "Product", "Quantity",
            "Unit Price", "Line Total", "Order Total", "Order Status",
            "Payment Status", "Payment Method", "Paid At", "Order Date",
        ])
        for row in rows:
            writer.writerow([
                csv_safe(row["order_number"]), csv_safe(row["customer_name"]),
                csv_safe(row["phone_number"]), csv_safe(row["product_name"]),
                row["quantity"], row["unit_price"], row["line_total"],
                row["order_total"], row["order_status"], row["payment_status"],
                row["payment_method"] or "", row["paid_at"] or "", row["order_date"],
            ])

        range_name = f"{from_date or 'all'}-to-{to_date or 'all'}"
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-Disposition":
                    f'attachment; filename="kikwetu-eggs-report-{range_name}.csv"'
            },
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except sqlite3.Error:
        return jsonify({"error": "Report export could not be generated"}), 500
