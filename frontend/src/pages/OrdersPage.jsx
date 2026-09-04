import { useEffect, useMemo, useState } from "react";
import { deleteOrder, getOrder, getOrders, recordOrderPayment, updateOrder } from "../api/orders.js";

const money = new Intl.NumberFormat("en-KE", { style: "currency", currency: "KES", minimumFractionDigits: 0 });
const dateFormat = new Intl.DateTimeFormat("en-KE", { dateStyle: "medium", timeStyle: "short" });
const formatDate = (value) => { if (!value) return "—"; const date = new Date(`${value.replace(" ", "T")}Z`); return Number.isNaN(date.getTime()) ? value : dateFormat.format(date); };
const title = (value) => value ? value.charAt(0).toUpperCase() + value.slice(1) : "Not selected";
const methodLabel = (value) => ({ mpesa: "M-Pesa", cash: "Cash", bank_transfer: "Bank Transfer" }[value] || "Not selected");

export default function OrdersPage() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [payment, setPayment] = useState("all");
  const [method, setMethod] = useState("all");
  const [details, setDetails] = useState(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [paymentOrder, setPaymentOrder] = useState(null);
  const [paymentMethod, setPaymentMethod] = useState("");
  const [acting, setActing] = useState(false);
  const [actionError, setActionError] = useState("");
  const [deleteOrderTarget, setDeleteOrderTarget] = useState(null);

  useEffect(() => { getOrders().then((data) => setOrders(data.orders || [])).catch(() => setError("Orders could not be loaded.")).finally(() => setLoading(false)); }, []);
  const summary = useMemo(() => ({ total: orders.length, pending: orders.filter((o) => o.order_status === "pending").length, processing: orders.filter((o) => o.order_status === "processing").length, completed: orders.filter((o) => o.order_status === "completed").length, cancelled: orders.filter((o) => o.order_status === "cancelled").length, paid: orders.filter((o) => o.payment_status === "paid").length, unpaid: orders.filter((o) => o.payment_status === "unpaid" && o.order_status !== "cancelled").length }), [orders]);
  const visible = useMemo(() => { const term = search.trim().toLowerCase(); return orders.filter((order) => (!term || order.order_number.toLowerCase().includes(term) || order.customer_name.toLowerCase().includes(term)) && (status === "all" || order.order_status === status) && (payment === "all" || order.payment_status === payment) && (method === "all" || order.payment_method === method)); }, [orders, search, status, payment, method]);

  async function view(orderId) { setDetailsLoading(true); setActionError(""); try { setDetails(await getOrder(orderId)); } catch { setActionError("Order details could not be loaded."); } finally { setDetailsLoading(false); } }
  function mergeOrder(updated) { setOrders((current) => current.map((order) => order.order_id === updated.order_id ? { ...order, ...updated } : order)); }
  async function setOrderStatus(order, nextStatus) {
    if (!window.confirm(`${title(nextStatus)} order ${order.order_number}?`)) return;
    setActing(true); setActionError("");
    try { const result = await updateOrder(order.order_id, { order_status: nextStatus }); mergeOrder(result); if (details?.order_id === order.order_id) setDetails(await getOrder(order.order_id)); setMessage(`Order ${order.order_number} marked as ${nextStatus}.`); }
    catch (requestError) { setActionError(requestError.message); } finally { setActing(false); }
  }
  async function recordPayment(event) {
    event.preventDefault(); if (!paymentMethod) return setActionError("Choose a payment method."); setActing(true); setActionError("");
    try { const result = await recordOrderPayment(paymentOrder.order_id, paymentMethod); mergeOrder(result); if (details?.order_id === result.order_id) setDetails(await getOrder(result.order_id)); setMessage(result.message); setPaymentOrder(null); setPaymentMethod(""); }
    catch (requestError) { setActionError(requestError.message); } finally { setActing(false); }
  }
  async function permanentlyDelete() {
    setActing(true); setActionError("");
    try { const result = await deleteOrder(deleteOrderTarget.order_id); setOrders((current) => current.filter((order) => order.order_id !== deleteOrderTarget.order_id)); if (details?.order_id === deleteOrderTarget.order_id) setDetails(null); setDeleteOrderTarget(null); setMessage(result.message); }
    catch (requestError) { setActionError(requestError.message); } finally { setActing(false); }
  }

  function orderActions(order) {
    const mpesaPending = order.mpesa_status === "pending";
    const cashConfirmation = order.order_status === "processing" && order.payment_status === "unpaid" && order.payment_method === "cash";
    const cancellable = ["pending", "processing"].includes(order.order_status) && order.payment_status === "unpaid" && !mpesaPending;
    return <div className="admin-order-actions"><button type="button" className="secondary-button" onClick={() => view(order.order_id)}>View Details</button>{cashConfirmation && <button type="button" onClick={() => { setPaymentOrder(order); setPaymentMethod("cash"); setActionError(""); }}>Confirm Cash Payment</button>}{cancellable && <button type="button" className="cancel-order-action" disabled={acting} onClick={() => setOrderStatus(order, "cancelled")}>Cancel</button>}{order.order_status === "cancelled" && <button type="button" className="delete-text-button" onClick={() => { setActionError(""); setDeleteOrderTarget(order); }}>Delete</button>}</div>;
  }

  return <>
    <section className="page-heading"><div><p className="eyebrow">Order management</p><h1>Orders</h1><p className="page-description">Manage customer orders, payments and fulfillment.</p></div></section>
    <section className="admin-summary-grid order-summary-grid">{[["Total Orders", summary.total, ""], ["Pending", summary.pending, "pending"], ["Processing", summary.processing, "processing"], ["Completed", summary.completed, "active"], ["Cancelled", summary.cancelled, "inactive"], ["Paid", summary.paid, "active"], ["Unpaid", summary.unpaid, "pending"]].map(([label, value, type]) => <article className={type ? `summary-${type}` : ""} key={label}><span>{label}</span><strong>{value}</strong></article>)}</section>
    {message && <p className="message success-message list-message" role="status">{message}</p>}{actionError && !paymentOrder && !deleteOrderTarget && <p className="message error-message list-message">{actionError}</p>}
    <section className="panel admin-list-panel"><div className="admin-toolbar order-filter-toolbar"><label className="search-field">Search orders<input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Order number or customer" /></label><label>Order status<select value={status} onChange={(e) => setStatus(e.target.value)}><option value="all">All Orders</option><option value="pending">Pending</option><option value="processing">Processing</option><option value="completed">Completed</option><option value="cancelled">Cancelled</option></select></label><label>Payment<select value={payment} onChange={(e) => setPayment(e.target.value)}><option value="all">All</option><option value="paid">Paid</option><option value="unpaid">Unpaid</option></select></label><label>Method<select value={method} onChange={(e) => setMethod(e.target.value)}><option value="all">All</option><option value="mpesa">M-Pesa</option><option value="cash">Cash</option><option value="bank_transfer">Bank Transfer</option></select></label></div>
      {loading && <p className="state-message">Loading orders…</p>}{error && <div className="state-message error-state"><strong>Orders unavailable.</strong><span>{error}</span></div>}{!loading && !error && visible.length === 0 && <div className="state-message empty-state"><strong>No matching orders.</strong><span>Try changing the filters.</span></div>}
      {!loading && !error && visible.length > 0 && <div className="admin-order-grid">{visible.map((order) => <article className="admin-order-card" key={order.order_id}><div className="admin-order-card-top"><div><span className="order-card-label">Order</span><h2>{order.order_number}</h2><p>{order.customer_name}</p></div><strong>{money.format(order.total_amount)}</strong></div><p className="order-item-summary">{order.item_summary} <span>· {order.quantity} unit{order.quantity === 1 ? "" : "s"}</span></p><div className="order-card-status"><span className={`status-badge status-${order.order_status}`}>{title(order.order_status)}</span><span className={`payment-badge payment-${order.payment_status}`}>{title(order.payment_status)}</span><span>{methodLabel(order.payment_method)}</span>{order.mpesa_status === "pending" && <span className="payment-badge payment-pending">M-Pesa Pending</span>}</div><time>{formatDate(order.created_at)}</time>{orderActions(order)}</article>)}</div>}
    </section>

    {(details || detailsLoading) && <div className="modal-backdrop" role="presentation"><div className="confirmation-dialog admin-order-detail-modal" role="dialog" aria-modal="true"><div className="dialog-title-row"><div><p className="eyebrow">Order details</p><h2>{details?.order_number || "Loading…"}</h2></div><button type="button" className="dialog-close" onClick={() => setDetails(null)} aria-label="Close">×</button></div>{detailsLoading ? <p className="state-message">Loading details…</p> : details && <><div className="detail-status-row"><span className={`status-badge status-${details.order_status}`}>{title(details.order_status)}</span><span className={`payment-badge payment-${details.payment_status}`}>{title(details.payment_status)}</span>{details.latest_mpesa?.status === "pending" && <span className="payment-badge payment-pending">M-Pesa Pending</span>}</div><dl className="details-grid"><div><dt>Customer</dt><dd>{details.customer.name}</dd></div><div><dt>Phone</dt><dd><a href={`tel:${details.customer.phone_number}`}>{details.customer.phone_number}</a></dd></div><div><dt>Payment Method</dt><dd>{methodLabel(details.payment_method)}</dd></div><div><dt>Order Date</dt><dd>{formatDate(details.created_at)}</dd></div>{details.mpesa_payment?.mpesa_receipt_number && <div><dt>M-Pesa Receipt</dt><dd>{details.mpesa_payment.mpesa_receipt_number}</dd></div>}<div className="detail-notes"><dt>Notes</dt><dd>{details.notes || "No notes"}</dd></div></dl><div className="detail-item-list"><h3>Items</h3>{details.items.map((item) => <div key={item.order_item_id}><span><strong>{item.product_name}</strong><small>{item.quantity} × {money.format(item.unit_price)} per {item.unit_name}</small></span><b>{money.format(item.line_total)}</b></div>)}<footer><span>Order Total</span><strong>{money.format(details.total_amount)}</strong></footer></div><div className="admin-order-actions detail-actions">{orderActions(details)}{details.order_status === "pending" && <button type="button" disabled={acting} onClick={() => setOrderStatus(details, "completed")}>Mark Completed</button>}</div></>}</div></div>}

    {paymentOrder && <div className="modal-backdrop" role="presentation"><form className="confirmation-dialog" onSubmit={recordPayment}><p className="eyebrow">Confirm payment</p><h2>{paymentOrder.payment_method === "cash" ? "Confirm Cash Payment" : "Record Payment"}</h2><p>Confirm receipt of {money.format(paymentOrder.total_amount)} for {paymentOrder.order_number}. This will complete a cash order.</p><label>Payment Method<select value={paymentMethod} onChange={(e) => setPaymentMethod(e.target.value)}><option value="cash">Cash</option><option value="bank_transfer">Bank Transfer</option></select></label>{actionError && <p className="message error-message">{actionError}</p>}<div className="dialog-actions"><button type="button" className="secondary-button" onClick={() => setPaymentOrder(null)}>Cancel</button><button type="submit" disabled={acting}>{acting ? "Confirming…" : "Confirm Payment"}</button></div></form></div>}
    {deleteOrderTarget && <div className="modal-backdrop" role="presentation"><div className="confirmation-dialog"><p className="eyebrow">Permanent action</p><h2>Delete cancelled order?</h2><p>This permanently removes {deleteOrderTarget.order_number}.</p>{actionError && <p className="message error-message">{actionError}</p>}<div className="dialog-actions"><button type="button" className="secondary-button" onClick={() => setDeleteOrderTarget(null)}>Cancel</button><button type="button" className="danger-button" disabled={acting} onClick={permanentlyDelete}>{acting ? "Deleting…" : "Delete Order"}</button></div></div></div>}
  </>;
}
