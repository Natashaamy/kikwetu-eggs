import { useEffect, useState } from "react";

import { downloadReportCsv, getReport } from "../api/reports.js";

const currencyFormatter = new Intl.NumberFormat("en-KE", {
  style: "currency",
  currency: "KES",
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});
const dateFormatter = new Intl.DateTimeFormat("en-KE", { dateStyle: "medium", timeStyle: "short" });

function isoDate(value) {
  const offset = value.getTimezoneOffset();
  return new Date(value.getTime() - offset * 60000).toISOString().slice(0, 10);
}

function formatAmount(value) {
  return currencyFormatter.format(Number(value || 0));
}

function formatDate(value) {
  if (!value) return "Not available";
  const parsed = new Date(`${value.replace(" ", "T")}Z`);
  return Number.isNaN(parsed.getTime()) ? value : dateFormatter.format(parsed);
}

function titleCase(value) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export default function ReportsPage() {
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);

  async function loadReport(nextFrom = fromDate, nextTo = toDate) {
    if (nextFrom && nextTo && nextFrom > nextTo) {
      setError("From date cannot be after to date.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      setReport(await getReport(nextFrom, nextTo));
    } catch (requestError) {
      setError(requestError.message || "Report data could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadReport("", "");
  }, []);

  function applyQuickRange(type) {
    const today = new Date();
    let start = null;
    let end = today;
    if (type === "today") start = today;
    if (type === "seven") start = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 6);
    if (type === "thirty") start = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 29);
    if (type === "month") start = new Date(today.getFullYear(), today.getMonth(), 1);
    if (type === "all") end = null;
    const nextFrom = start ? isoDate(start) : "";
    const nextTo = end ? isoDate(end) : "";
    setFromDate(nextFrom);
    setToDate(nextTo);
    loadReport(nextFrom, nextTo);
  }

  async function exportReport() {
    setExporting(true);
    setError("");
    try {
      const reportBlob = await downloadReportCsv(fromDate, toDate);
      const downloadUrl = URL.createObjectURL(reportBlob);
      const link = document.createElement("a");
      link.href = downloadUrl;
      link.download = `kikwetu-eggs-report-${fromDate || "all"}-to-${toDate || "all"}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(downloadUrl);
    } catch (requestError) {
      setError(requestError.message || "The report export could not be downloaded.");
    } finally {
      setExporting(false);
    }
  }

  const summary = report?.summary;
  const statusRows = summary ? [
    ["pending", summary.pending_orders],
    ["processing", summary.processing_orders],
    ["completed", summary.completed_orders],
    ["cancelled", summary.cancelled_orders],
  ] : [];
  const hasData = Boolean(summary?.total_orders);
  const maxDailyRevenue = Math.max(1, ...(report?.sales_over_time || []).map((row) => Number(row.revenue)));

  return <>
    <section className="page-heading">
      <div><p className="eyebrow">Business intelligence</p><h1>Reports &amp; Analytics</h1><p className="page-description">Track sales, orders, payments and business performance.</p></div>
      {report && <button type="button" className="export-report-button" onClick={exportReport} disabled={exporting}>{exporting ? "Exporting…" : "Export CSV"}</button>}
    </section>

    <section className="report-controls" aria-label="Report date range">
      <form className="report-date-form" onSubmit={(event) => { event.preventDefault(); loadReport(); }}>
        <label>From Date<input type="date" value={fromDate} max={toDate || undefined} onChange={(event) => setFromDate(event.target.value)} /></label>
        <label>To Date<input type="date" value={toDate} min={fromDate || undefined} onChange={(event) => setToDate(event.target.value)} /></label>
        <button type="submit" disabled={loading}>{loading ? "Generating…" : "Generate Report"}</button>
      </form>
      <div className="report-quick-filters" aria-label="Quick date filters">
        {[['today', 'Today'], ['seven', 'Last 7 Days'], ['thirty', 'Last 30 Days'], ['month', 'This Month'], ['all', 'All Time']].map(([value, label]) => <button key={value} type="button" className="filter-button" onClick={() => applyQuickRange(value)} disabled={loading}>{label}</button>)}
      </div>
    </section>

    {error && <div className="state-message error-state panel" role="alert"><strong>Report unavailable.</strong><span>{error}</span></div>}
    {loading && !report && <section className="panel"><p className="state-message">Generating report…</p></section>}

    {summary && <div className="report-content">
      <section className="stats-grid report-stats" aria-label="Sales summary">
        {[
          ["Total Orders", summary.total_orders, "total"],
          ["Total Revenue", formatAmount(summary.completed_revenue), "revenue"],
          ["Paid Orders", summary.paid_orders, "completed"],
          ["Unpaid Orders", summary.unpaid_orders, "pending"],
        ].map(([label, value, type]) => <article className={`stat-card stat-${type}`} key={label}><span>{label}</span><strong>{value}</strong></article>)}
      </section>

      {!hasData ? <div className="state-message empty-state panel"><strong>No report data found for this period.</strong><span>Choose another date range to review business activity.</span></div> : <>
        <section className="panel report-status-panel"><div className="panel-heading"><p className="section-number">01</p><div><h2>Order Status Summary</h2><p>Share of all orders in the selected period.</p></div></div><div className="status-report">
          {statusRows.map(([status, count]) => {
            const percentage = summary.total_orders ? (count / summary.total_orders) * 100 : 0;
            return <div className="status-report-row" key={status}><div><strong>{titleCase(status)}</strong><span>{count} {count === 1 ? "order" : "orders"} · {percentage.toFixed(1)}%</span></div><div className="status-track"><span className={`status-fill status-fill-${status}`} style={{ width: `${percentage}%` }} /></div></div>;
          })}
        </div></section>

        <section className="panel analytics-chart-panel"><div className="panel-heading"><p className="section-number">02</p><div><h2>Sales Overview</h2><p>Completed-order revenue over the selected period.</p></div></div>{report.sales_over_time.length === 0 ? <p className="state-message">No completed sales in this period.</p> : <div className="sales-bars">{report.sales_over_time.map((day) => <div className="sales-bar-row" key={day.sale_date}><time>{day.sale_date}</time><div><span style={{ width: `${Math.max(3, Number(day.revenue) / maxDailyRevenue * 100)}%` }} /></div><strong>{formatAmount(day.revenue)}</strong></div>)}</div>}</section>

        <section className="panel report-status-panel"><div className="panel-heading"><p className="section-number">03</p><div><h2>Payments by Method</h2><p>Amounts recorded as paid in the selected period.</p></div></div>{report.payment_methods.length === 0 ? <p className="state-message">No payments recorded in this period.</p> : <div className="payment-method-summary">{report.payment_methods.map((method) => <div key={method.payment_method}><strong>{{ cash: "Cash", mpesa: "M-Pesa", bank_transfer: "Bank Transfer" }[method.payment_method]}</strong><span>{method.paid_orders} paid {method.paid_orders === 1 ? "order" : "orders"}</span><b>{formatAmount(method.amount)}</b></div>)}</div>}</section>

        <section className="panel"><div className="panel-heading"><p className="section-number">04</p><div><h2>Detailed Orders</h2><p>Recent activity for the selected period.</p></div></div><div className="table-wrapper"><table><thead><tr><th>Order</th><th>Customer</th><th>Date</th><th>Total</th><th>Status</th><th>Payment</th><th>Method</th></tr></thead><tbody>{report.recent_orders.map((order) => <tr key={order.order_number}><td data-label="Order"><strong>{order.order_number}</strong></td><td data-label="Customer">{order.customer_name}</td><td data-label="Date">{formatDate(order.created_at)}</td><td data-label="Total" className="price-cell">{formatAmount(order.total_amount)}</td><td data-label="Status"><span className={`status-badge status-${order.order_status}`}>{titleCase(order.order_status)}</span></td><td data-label="Payment"><span className={`payment-badge payment-${order.payment_status}`}>{titleCase(order.payment_status)}</span></td><td data-label="Method">{{ cash: "Cash", mpesa: "M-Pesa", bank_transfer: "Bank Transfer" }[order.payment_method] || "—"}</td></tr>)}</tbody></table></div></section>

        <section className="panel"><div className="panel-heading"><p className="section-number">02</p><div><h2>Top Selling Products</h2><p>Completed sales ranked by units sold.</p></div></div>
          {report.top_products.length === 0 ? <p className="state-message">No completed product sales in this period.</p> : <div className="table-wrapper"><table><thead><tr><th>Rank</th><th>Product</th><th>Units Sold</th><th>Current Stock</th><th>Completed Orders</th><th>Revenue</th></tr></thead><tbody>{report.top_products.map((product, index) => <tr key={product.product_id}><td data-label="Rank"><strong>#{index + 1}</strong></td><td data-label="Product"><strong>{product.name}</strong><span className="product-description">Per {product.unit_name}</span></td><td data-label="Units Sold">{product.units_sold} {product.unit_name}{product.units_sold === 1 ? "" : "s"}</td><td data-label="Stock">{product.stock_quantity}</td><td data-label="Orders">{product.completed_orders}</td><td data-label="Revenue" className="price-cell">{formatAmount(product.revenue)}</td></tr>)}</tbody></table></div>}
        </section>

        <section className="panel"><div className="panel-heading"><p className="section-number">03</p><div><h2>Top Customers</h2><p>Customers ranked by completed-order spending.</p></div></div>
          {report.top_customers.length === 0 ? <p className="state-message">No completed customer sales in this period.</p> : <div className="table-wrapper"><table><thead><tr><th>Customer</th><th>Phone</th><th>Completed Orders</th><th>Total Spent</th><th>Last Completed Order</th></tr></thead><tbody>{report.top_customers.map((customer) => <tr key={customer.customer_id}><td data-label="Customer"><strong>{customer.name}</strong></td><td data-label="Phone"><a className="phone-link" href={`tel:${customer.phone_number}`}>{customer.phone_number}</a></td><td data-label="Orders">{customer.completed_orders}</td><td data-label="Total Spent" className="price-cell">{formatAmount(customer.total_spent)}</td><td data-label="Last Order">{formatDate(customer.last_completed_order)}</td></tr>)}</tbody></table></div>}
        </section>

        <section className="panel"><div className="panel-heading"><p className="section-number">04</p><div><h2>Recent Completed Sales</h2><p>The ten most recently updated completed orders.</p></div></div>
          {report.recent_completed_orders.length === 0 ? <p className="state-message">No completed sales in this period.</p> : <div className="table-wrapper"><table><thead><tr><th>Order Number</th><th>Customer</th><th>Total</th><th>Completed/Updated</th></tr></thead><tbody>{report.recent_completed_orders.map((order) => <tr key={order.order_id}><td data-label="Order"><strong>{order.order_number}</strong></td><td data-label="Customer">{order.customer_name}</td><td data-label="Total" className="price-cell">{formatAmount(order.total_amount)}</td><td data-label="Updated">{formatDate(order.completed_date)}</td></tr>)}</tbody></table></div>}
        </section>
      </>}
    </div>}
  </>;
}
