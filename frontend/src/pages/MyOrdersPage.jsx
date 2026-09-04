import { useEffect, useRef, useState } from "react";

import { cancelCustomerOrder, getCustomerOrders } from "../api/customerPortal.js";
import { getMpesaPaymentStatus, sendMpesaPrompt } from "../api/payments.js";
import { useAuth } from "../context/AuthContext.jsx";
import { CustomerOrdersTable } from "./CustomerDashboardPage.jsx";

const money = new Intl.NumberFormat("en-KE", { style: "currency", currency: "KES", minimumFractionDigits: 0 });
const wait = (milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));

export default function MyOrdersPage() {
  const { user } = useAuth();
  const mounted = useRef(true);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [cancellingId, setCancellingId] = useState(null);
  const [paymentOrder, setPaymentOrder] = useState(null);
  const [sendingPayment, setSendingPayment] = useState(false);
  const [checkingId, setCheckingId] = useState(null);
  const [paymentResult, setPaymentResult] = useState(null);

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
        ? { ...order, mpesa_status: "pending", checkout_request_id: result.checkout_request_id }
        : order) }));
      pollPayment(result.checkout_request_id, orderId);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSendingPayment(false);
    }
  }

  function orderActions(order) {
    const paymentPending = order.payment_status === "unpaid" && order.mpesa_status === "pending";
    const canPay = order.payment_status === "unpaid" && order.order_status !== "cancelled" && !paymentPending;
    const canCancel = order.order_status === "pending" && order.payment_status === "unpaid" && !paymentPending;
    return (
      <div className="row-actions customer-order-actions">
        {canPay && <button type="button" onClick={() => { setPaymentOrder(order); setError(""); setPaymentResult(null); }}>Pay with M-Pesa</button>}
        {paymentPending && <button type="button" className="secondary-button" disabled={checkingId === order.order_id} onClick={() => checkPayment(order.checkout_request_id, order.order_id)}>{checkingId === order.order_id ? "Checking…" : "Check Payment Status"}</button>}
        {canCancel && <button type="button" className="danger-button" disabled={cancellingId === order.order_id} onClick={() => cancelOrder(order)}>{cancellingId === order.order_id ? "Cancelling…" : "Cancel Order"}</button>}
      </div>
    );
  }

  return <>
    <section className="page-heading"><div><p className="eyebrow">Customer Portal</p><h1>My Orders</h1><p className="page-description">Review your orders, pay securely with M-Pesa, or cancel an eligible order.</p></div></section>
    {error && <p className="message error-message list-message">{error}</p>}
    {message && <p className="message success-message list-message" role="status">{message}</p>}
    {paymentResult && <section className="panel payment-success-panel" aria-labelledby="payment-success-heading"><p className="eyebrow">Payment Successful</p><h2 id="payment-success-heading">{paymentResult.order_number}</h2><dl className="details-grid"><div><dt>Amount</dt><dd>{money.format(paymentResult.amount)}</dd></div><div><dt>Payment Method</dt><dd>M-Pesa</dd></div><div><dt>Receipt</dt><dd>{paymentResult.mpesa_receipt_number}</dd></div><div><dt>Status</dt><dd><span className="payment-badge payment-paid">Paid</span></dd></div></dl></section>}
    <section className="panel">{!data ? <p className="state-message">Loading your orders…</p> : <CustomerOrdersTable orders={data.orders} actions={orderActions} />}</section>
    {paymentOrder && <div className="modal-backdrop" role="presentation"><div className="confirmation-dialog" role="dialog" aria-modal="true" aria-labelledby="mpesa-heading"><p className="eyebrow">M-Pesa Payment</p><h2 id="mpesa-heading">Pay {money.format(paymentOrder.total_amount)} with M-Pesa?</h2><p>Phone: <strong>{user?.phone_number}</strong></p><p className="helper-text">We will send a secure M-Pesa prompt to this phone. Enter your PIN only in the M-Pesa prompt—never in Kikwetu Eggs.</p><div className="dialog-actions"><button type="button" className="secondary-button" onClick={() => setPaymentOrder(null)} disabled={sendingPayment}>Cancel</button><button type="button" onClick={initiatePayment} disabled={sendingPayment}>{sendingPayment ? "Sending prompt…" : "Send M-Pesa Prompt"}</button></div></div></div>}
  </>;
}
