import { useCallback, useEffect, useState } from "react";

import { getDashboard } from "../api/dashboard.js";

const currencyFormatter = new Intl.NumberFormat("en-KE", {
  style: "currency",
  currency: "KES",
  minimumFractionDigits: 0,
});

const dateFormatter = new Intl.DateTimeFormat("en-KE", {
  dateStyle: "medium",
  timeStyle: "short",
});

function formatAmount(amount) {
  return currencyFormatter.format(Number(amount || 0));
}

function formatDate(date) {
  if (!date) {
    return "Not available";
  }

  const parsedDate = new Date(`${date.replace(" ", "T")}Z`);
  return Number.isNaN(parsedDate.getTime()) ? date : dateFormatter.format(parsedDate);
}

function formatStatus(status) {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function DashboardPage() {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      setSummary(await getDashboard());
    } catch {
      setError("Dashboard information could not be loaded. Please try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  const stats = summary
    ? [
        ["Total Orders", summary.total_orders, "total"],
        ["Pending", summary.pending_orders, "pending"],
        ["Completed", summary.completed_orders, "completed"],
        ["Cancelled", summary.cancelled_orders, "cancelled"],
        ["Products", `${summary.active_products} of ${summary.total_products} active`, "products"],
        ["Low Stock", summary.low_stock_products, "pending"],
        ["Out of Stock", summary.out_of_stock_products, "cancelled"],
        ["Paid Orders", summary.paid_orders, "completed"],
        ["Unpaid Orders", summary.unpaid_orders, "pending"],
        ["Payments Received", formatAmount(summary.payments_received), "revenue"],
        ["Outstanding Amount", formatAmount(summary.outstanding_amount), "cancelled"],
        ["Completed Revenue", formatAmount(summary.completed_revenue), "revenue"],
      ]
    : [];

  return (
    <>
      <section className="page-heading dashboard-heading">
        <div>
          <p className="eyebrow">Admin overview</p>
          <h1>Kikwetu Eggs Admin Dashboard</h1>
          <p className="page-description">Overview of your business.</p>
        </div>
        <button
          type="button"
          className="secondary-button dashboard-refresh"
          onClick={loadDashboard}
          disabled={loading}
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </section>

      {loading && !summary && (
        <section className="panel">
          <p className="state-message">Loading dashboard…</p>
        </section>
      )}

      {error && (
        <div className="state-message error-state panel" role="alert">
          <strong>Dashboard unavailable.</strong>
          <span>{error}</span>
          <button type="button" onClick={loadDashboard}>Try Again</button>
        </div>
      )}

      {summary && (
        <div className="dashboard-content">
          <section className="stats-grid" aria-label="Business statistics">
            {stats.map(([label, value, type]) => (
              <article className={`stat-card stat-${type}`} key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
              </article>
            ))}
          </section>

          {summary.inventory_attention.length > 0 && (
            <section className="panel" aria-labelledby="inventory-attention-heading">
              <div className="panel-heading"><p className="section-number">01</p><div><h2 id="inventory-attention-heading">Products Needing Attention</h2><p>Products at or below their low-stock threshold.</p></div></div>
              <div className="inventory-attention-list">{summary.inventory_attention.map((product) => <div key={product.product_id}><strong>{product.name}</strong><span className={`stock-badge ${product.stock_quantity === 0 ? "stock-out" : "stock-low"}`}>{product.stock_quantity === 0 ? "Out of Stock" : `${product.stock_quantity} ${product.unit_name}${product.stock_quantity === 1 ? "" : "s"} remaining`}</span></div>)}</div>
            </section>
          )}

          <section className="panel" aria-labelledby="recent-orders-heading">
            <div className="panel-heading">
              <p className="section-number">02</p>
              <div>
                <h2 id="recent-orders-heading">Recent Orders</h2>
                <p>The five most recently placed orders.</p>
              </div>
            </div>

            {summary.recent_orders.length === 0 ? (
              <div className="state-message empty-state">
                <strong>No orders yet.</strong>
                <span>New customer orders will appear here.</span>
              </div>
            ) : (
              <div className="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>Order Number</th>
                      <th>Customer</th>
                      <th>Status</th>
                      <th>Total</th>
                      <th>Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.recent_orders.map((order) => (
                      <tr key={order.order_id}>
                        <td data-label="Order"><strong>{order.order_number}</strong></td>
                        <td data-label="Customer">{order.customer_name}</td>
                        <td data-label="Status">
                          <span className={`status-badge status-${order.order_status}`}>
                            {formatStatus(order.order_status)}
                          </span>
                        </td>
                        <td data-label="Total" className="price-cell">
                          {formatAmount(order.total_amount)}
                        </td>
                        <td data-label="Date">{formatDate(order.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}
    </>
  );
}

export default DashboardPage;
