import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getCustomerDashboard } from "../api/customerPortal.js";
import { useAuth } from "../context/AuthContext.jsx";

const money = new Intl.NumberFormat("en-KE", { style: "currency", currency: "KES", minimumFractionDigits: 0 });

export function CustomerOrdersTable({ orders, actions, highlightedOrderId }) {
  if (!orders.length) return <div className="state-message empty-state"><strong>No orders yet.</strong><span>Your orders will appear here.</span></div>;
  return <div className="table-wrapper"><table><thead><tr><th>Order Number</th><th>Product(s)</th><th>Quantity</th><th>Total</th><th>Order Status</th><th>Payment</th><th>Method</th><th>Date</th>{actions && <th>Action</th>}</tr></thead><tbody>{orders.map((order) => <tr className={order.order_id === highlightedOrderId ? "highlighted-order" : ""} key={order.order_id}><td data-label="Order"><strong>{order.order_number}</strong>{order.order_id === highlightedOrderId && <span className="new-order-label">New</span>}</td><td data-label="Products">{order.products}</td><td data-label="Quantity">{order.quantity}</td><td data-label="Total" className="price-cell">{money.format(order.total_amount)}</td><td data-label="Status"><span className={`status-badge status-${order.order_status}`}>{order.order_status.charAt(0).toUpperCase() + order.order_status.slice(1)}</span></td><td data-label="Payment"><span className={`payment-badge payment-${order.payment_status === "paid" ? "paid" : order.mpesa_status === "pending" ? "pending" : "unpaid"}`}>{order.payment_status === "paid" ? "Paid" : order.mpesa_status === "pending" ? "Payment Pending" : "Unpaid"}</span>{order.mpesa_receipt_number && <small className="receipt-reference">Receipt: {order.mpesa_receipt_number}</small>}</td><td data-label="Method">{order.payment_method ? order.payment_method === "mpesa" ? "M-Pesa" : order.payment_method.charAt(0).toUpperCase() + order.payment_method.slice(1) : "Not selected"}</td><td data-label="Date">{order.created_at}</td>{actions && <td data-label="Action">{actions(order)}</td>}</tr>)}</tbody></table></div>;
}

export default function CustomerDashboardPage() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => { getCustomerDashboard().then(setData).catch(() => setError("Your order summary could not be loaded.")); }, []);
  if (error) return <div className="state-message error-state panel"><strong>Dashboard unavailable.</strong><span>{error}</span></div>;
  if (!data) return <section className="panel"><p className="state-message">Loading your dashboard…</p></section>;
  const stats = [["Pending Orders", data.pending_orders, "pending"], ["Completed Orders", data.completed_orders, "completed"], ["Cancelled Orders", data.cancelled_orders, "cancelled"], ["Unpaid Orders", data.unpaid_orders, "pending"], ["Amount Outstanding", money.format(data.amount_outstanding), "cancelled"], ["Total Amount Spent", money.format(data.total_amount_spent), "revenue"]];
  return <><section className="page-heading"><div><p className="eyebrow">Welcome, {user?.name}</p><h1>Dashboard</h1><p className="page-description">Your orders at a glance.</p></div><Link className="primary-link" to="/customer/order-now">Order Now</Link></section><div className="dashboard-content"><section className="stats-grid customer-stats">{stats.map(([label, value, type]) => <article className={`stat-card stat-${type}`} key={label}><span>{label}</span><strong>{value}</strong></article>)}</section><section className="panel"><div className="panel-heading"><p className="section-number">01</p><div><h2>Recent Orders</h2><p>Your five most recent orders.</p></div></div><CustomerOrdersTable orders={data.recent_orders} /></section></div></>;
}
