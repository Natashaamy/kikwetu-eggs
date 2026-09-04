import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { cancelCustomerOrder, getCustomerOrders, selectCashPayment } from "../api/customerPortal.js";
import { getMpesaPaymentStatus, sendMpesaPrompt } from "../api/payments.js";
import { useAuth } from "../context/AuthContext.jsx";

const money = new Intl.NumberFormat("en-KE", { style: "currency", currency: "KES", minimumFractionDigits: 0 });
const wait = (milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));

export default function MyOrdersPage() {
  const { user } = useAuth();
  const location = useLocation();
  const newOrder = location.state?.newlyCreatedOrder;
  const updatedOrder = location.state?.updatedOrder;
  const highlightedOrderId = newOrder?.order_id || updatedOrder?.order_id;
  const mounted = useRef(true);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [cancellingId, setCancellingId] = useState(null);
  const [paymentOrder, setPaymentOrder] = useState(null);
  const [sendingPayment, setSendingPayment] = useState(false);
  const [checkingId, setCheckingId] = useState(null);
  const [paymentResult, setPaymentResult] = useState(null);
  const [selectingCashId, setSelectingCashId] = useState(null);

  async function loadOrders() {
    try {
      const result = await getCustomerOrders();
      if (mounted.current) { setData(result); setError(""); }
    } catch {
      if (mounted.current) setError("Your orders could not be loaded.");
    }
  }

  useEffect(() => {
    mounted.current = true;
    loadOrders();
    return () => { mounted.current = false; };
  }, []);

  async function cancelOrder(order) {
    if (!window.confirm("Are you sure you want to cancel this order?")) return;
    setCancellingId(order.order_id);
    setError("");
    try {
      const result = await cancelCustomerOrder(order.order_id);
      setMessage(result.message);
      await loadOrders();
    } catch (requestError) {
      setError(requestError.message || "This order could not be cancelled.");
    } finally {
      setCancellingId(null);
    }
  }

  async function checkPayment(checkoutRequestId, orderId, quiet = false) {
    if (!quiet) setCheckingId(orderId);
    try {
      const result = await getMpesaPaymentStatus(checkoutRequestId);
      if (!mounted.current) return result;
      if (result.status === "successful") {
        setPaymentResult(result);
        setMessage("Payment successful.");
        await loadOrders();
      } else if (["failed", "cancelled"].includes(result.status)) {
        setError(result.result_description || "The M-Pesa payment was not completed. You can try again.");
        await loadOrders();
      }
      return result;
    } catch (requestError) {
      if (!quiet && mounted.current) setError(requestError.message);
      return null;
    } finally {
      if (!quiet && mounted.current) setCheckingId(null);
    }
  }

  async function pollPayment(checkoutRequestId, orderId) {
    for (let attempt = 0; attempt < 6 && mounted.current; attempt += 1) {
      await wait(5000);
      if (!mounted.current) return;
      const result = await checkPayment(checkoutRequestId, orderId, true);
      if (!result || ["successful", "failed", "cancelled"].includes(result.status)) return;
    }
  }

  async function initiatePayment() {
    if (!paymentOrder) return;
    const orderId = paymentOrder.order_id;
    setSendingPayment(true);
    setError("");
    setMessage("");
    try {
      const result = await sendMpesaPrompt(orderId);
      setPaymentOrder(null);
      setMessage("Payment request sent. Check your phone and enter your M-Pesa PIN.");
      setData((current) => ({ ...current, orders: current.orders.map((order) => order.order_id === orderId
        ? { ...order, order_status: "processing", payment_method: "mpesa", mpesa_status: "pending", checkout_request_id: result.checkout_request_id }
        : order) }));
      pollPayment(result.checkout_request_id, orderId);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSendingPayment(false);
    }
  }

  async function chooseCash(order) {
    if (!window.confirm("Choose cash payment for this order? Payment will remain unpaid until the admin confirms it.")) return;
    setSelectingCashId(order.order_id);
    setError("");
    setMessage("");
    try {
      const result = await selectCashPayment(order.order_id);
      setMessage(result.message);
      await loadOrders();
    } catch (requestError) {
      setError(requestError.message || "Cash payment could not be selected.");
    } finally {
      setSelectingCashId(null);
    }
  }

  function availableActions(order) {
    const paymentPending = order.payment_status === "unpaid" && order.mpesa_status === "pending";
    const canPayMpesa = order.payment_status === "unpaid" && order.order_status !== "cancelled" && order.payment_method !== "cash" && !paymentPending;
    const canChooseCash = order.payment_status === "unpaid" && ["pending", "processing"].includes(order.order_status) && order.payment_method !== "cash" && !paymentPending;
    const canEdit = order.payment_status === "unpaid" && ["pending", "processing"].includes(order.order_status) && !paymentPending;
    const canCancel = ["pending", "processing"].includes(order.order_status) && order.payment_status === "unpaid" && !paymentPending;
    return { paymentPending, canPayMpesa, canChooseCash, canEdit, canCancel };
  }

  function OrderCard({ order }) {
    const actions = availableActions(order);
    const finished = order.order_status === "completed" && order.payment_status === "paid";
    return <article className={`customer-order-card ${order.order_id === highlightedOrderId ? "highlighted-order-card" : ""}`}>
      <div className="customer-order-card-header"><div><span className="order-card-label">Order</span><h2>{order.order_number}{order.order_id === highlightedOrderId && <span className="new-order-label">{updatedOrder ? "Updated" : "New"}</span>}</h2><p>{order.products}</p></div><div className="order-card-total"><span>Total</span><strong>{money.format(order.total_amount)}</strong></div></div>
      <div className="order-card-status"><span className={`status-badge status-${order.order_status}`}>{order.order_status.charAt(0).toUpperCase() + order.order_status.slice(1)}</span><span className={`payment-badge payment-${order.payment_status === "paid" ? "paid" : actions.paymentPending ? "pending" : "unpaid"}`}>{actions.paymentPending ? "Payment Pending" : order.payment_status === "paid" ? "Paid" : "Unpaid"}</span><span className="order-date">{order.created_at}</span></div>
      <dl className="order-card-details"><div><dt>Quantity</dt><dd>{order.quantity}</dd></div><div><dt>Payment method</dt><dd>{order.payment_method ? order.payment_method === "mpesa" ? "M-Pesa" : order.payment_method.charAt(0).toUpperCase() + order.payment_method.slice(1) : "Not selected"}</dd></div>{order.mpesa_receipt_number && <div><dt>Receipt</dt><dd>{order.mpesa_receipt_number}</dd></div>}</dl>
      {actions.paymentPending ? <div className="payment-progress"><div><strong>Payment in progress</strong><span>Waiting for M-Pesa confirmation. Complete or cancel the prompt before editing this order.</span></div><button type="button" className="secondary-button" disabled={checkingId === order.order_id} onClick={() => checkPayment(order.checkout_request_id, order.order_id)}>{checkingId === order.order_id ? "Checking…" : "Check Payment Status"}</button></div>
        : !finished && order.order_status !== "cancelled" && <div className="order-action-panel"><h3>Payment &amp; Actions</h3><div className="payment-action-grid">{actions.canPayMpesa && <button type="button" className="mpesa-action" onClick={() => { setPaymentOrder(order); setError(""); setPaymentResult(null); }}>{order.payment_method === "mpesa" ? "Retry M-Pesa" : "Pay with M-Pesa"}</button>}{actions.canChooseCash && <button type="button" className="cash-button" disabled={selectingCashId === order.order_id} onClick={() => chooseCash(order)}>{selectingCashId === order.order_id ? "Selecting…" : "Pay with Cash"}</button>}{actions.canEdit && <Link className="edit-order-action" to={`/customer/order-now?edit=${order.order_id}`} state={{ editOrderId: order.order_id }}>Edit Order</Link>}{actions.canCancel && <button type="button" className="cancel-order-action" disabled={cancellingId === order.order_id} onClick={() => cancelOrder(order)}>{cancellingId === order.order_id ? "Cancelling…" : "Cancel Order"}</button>}</div></div>}
    </article>;
  }

  return <>
    <section className="page-heading"><div><p className="eyebrow">Customer Portal</p><h1>My Orders</h1><p className="page-description">Review your orders, pay securely with M-Pesa, or cancel an eligible order.</p></div></section>
    {error && <p className="message error-message list-message">{error}</p>}
    {newOrder && <p className="message success-message list-message" role="status">Order {newOrder.order_number} was placed successfully. Choose how you would like to pay.</p>}
    {updatedOrder && <p className="message success-message list-message" role="status">Order {updatedOrder.order_number} was updated successfully. Its new total is {money.format(updatedOrder.total_amount)}.</p>}
    {message && <p className="message success-message list-message" role="status">{message}</p>}
    {paymentResult && <section className="panel payment-success-panel" aria-labelledby="payment-success-heading"><p className="eyebrow">Payment Successful</p><h2 id="payment-success-heading">{paymentResult.order_number}</h2><dl className="details-grid"><div><dt>Amount</dt><dd>{money.format(paymentResult.amount)}</dd></div><div><dt>Payment Method</dt><dd>M-Pesa</dd></div><div><dt>Receipt</dt><dd>{paymentResult.mpesa_receipt_number}</dd></div><div><dt>Status</dt><dd><span className="payment-badge payment-paid">Paid</span></dd></div></dl></section>}
    {!data ? <section className="panel"><p className="state-message">Loading your orders…</p></section> : data.orders.length === 0 ? <section className="panel"><div className="state-message empty-state"><strong>No orders yet.</strong><span>Your orders will appear here.</span></div></section> : <section className="customer-orders-grid" aria-label="Your orders">{data.orders.map((order) => <OrderCard order={order} key={order.order_id} />)}</section>}
    {paymentOrder && <div className="modal-backdrop" role="presentation"><div className="confirmation-dialog" role="dialog" aria-modal="true" aria-labelledby="mpesa-heading"><p className="eyebrow">M-Pesa Payment</p><h2 id="mpesa-heading">Pay {money.format(paymentOrder.total_amount)} with M-Pesa?</h2><p>Phone: <strong>{user?.phone_number}</strong></p><p className="helper-text">We will send a secure M-Pesa prompt to this phone. Enter your PIN only in the M-Pesa prompt—never in Kikwetu Eggs.</p><div className="dialog-actions"><button type="button" className="secondary-button" onClick={() => setPaymentOrder(null)} disabled={sendingPayment}>Cancel</button><button type="button" onClick={initiatePayment} disabled={sendingPayment}>{sendingPayment ? "Sending prompt…" : "Send M-Pesa Prompt"}</button></div></div></div>}
  </>;
}
