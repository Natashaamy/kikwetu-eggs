import { useEffect, useState } from "react";

import { deleteOrder, getOrder, getOrders, recordOrderPayment, updateOrder } from "../api/orders.js";

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
  return currencyFormatter.format(Number(amount));
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

function quantityWithUnit(quantity, unit) {
  return `${quantity} ${unit}${quantity === 1 ? "" : "s"}`;
}

function paymentMethodLabel(method) {
  return { cash: "Cash", mpesa: "M-Pesa", bank_transfer: "Bank Transfer" }[method] || "Not recorded";
}

function OrdersPage() {
  const [orders, setOrders] = useState([]);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [detailsError, setDetailsError] = useState("");
  const [statusUpdating, setStatusUpdating] = useState(false);
  const [statusError, setStatusError] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [statusFilter, setStatusFilter] = useState("active");
  const [orderToDelete, setOrderToDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteMessage, setDeleteMessage] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [paymentFilter, setPaymentFilter] = useState("all");
  const [paymentOrder, setPaymentOrder] = useState(null);
  const [paymentMethod, setPaymentMethod] = useState("");
  const [paymentRecording, setPaymentRecording] = useState(false);
  const [paymentError, setPaymentError] = useState("");

  const filteredOrders = orders.filter((order) => {
    if (paymentFilter !== "all" && order.payment_status !== paymentFilter) return false;
    if (statusFilter === "all") {
      return true;
    }

    if (statusFilter === "active") {
      return ["pending", "completed"].includes(order.order_status);
    }

    return order.order_status === statusFilter;
  });

  useEffect(() => {
    let ignoreResult = false;

    async function loadOrders() {
      try {
        const data = await getOrders();
        if (!ignoreResult) {
          setOrders(data.orders || []);
        }
      } catch {
        if (!ignoreResult) {
          setLoadError("Orders could not be loaded. Check that the backend is running.");
        }
      } finally {
        if (!ignoreResult) {
          setLoading(false);
        }
      }
    }

    loadOrders();

    return () => {
      ignoreResult = true;
    };
  }, []);

  async function handleViewOrder(orderId) {
    setDetailsLoading(true);
    setDetailsError("");
    setStatusError("");
    setStatusMessage("");
    setSelectedOrder(null);

    try {
      const order = await getOrder(orderId);
      setSelectedOrder(order);
    } catch {
      setDetailsError("This order could not be loaded. Please try again.");
    } finally {
      setDetailsLoading(false);
    }
  }

  async function handleMarkCompleted() {
    if (!selectedOrder) {
      return;
    }

    const confirmed = window.confirm("Mark this order as completed?");

    if (!confirmed) {
      return;
    }

    setStatusUpdating(true);
    setStatusError("");
    setStatusMessage("");

    try {
      const updatedOrder = await updateOrder(selectedOrder.order_id, {
        order_status: "completed",
      });
      setSelectedOrder(await getOrder(updatedOrder.order_id));
      setOrders((currentOrders) =>
        currentOrders.map((order) =>
          order.order_id === updatedOrder.order_id ? { ...order, ...updatedOrder } : order,
        ),
      );
      setStatusMessage("Order marked as completed.");
    } catch {
      setStatusError("The order status could not be updated. Please try again.");
    } finally {
      setStatusUpdating(false);
    }
  }

  async function handleDeleteOrder() {
    if (!orderToDelete) {
      return;
    }

    setDeleting(true);
    setDeleteError("");

    try {
      const result = await deleteOrder(orderToDelete.order_id);
      setOrders((currentOrders) =>
        currentOrders.filter((order) => order.order_id !== orderToDelete.order_id),
      );
      setSelectedOrder(null);
      setOrderToDelete(null);
      setDeleteMessage(`${result.message}.`);
    } catch (error) {
      setDeleteError(error.message || "The cancelled order could not be deleted.");
    } finally {
      setDeleting(false);
    }
  }

  async function handleRecordPayment(event) {
    event.preventDefault();
    if (!paymentMethod) {
      setPaymentError("Choose a payment method.");
      return;
    }
    setPaymentRecording(true);
    setPaymentError("");
    try {
      const result = await recordOrderPayment(paymentOrder.order_id, paymentMethod);
      setOrders((current) => current.map((order) => order.order_id === result.order_id ? { ...order, ...result } : order));
      if (selectedOrder?.order_id === result.order_id) setSelectedOrder(await getOrder(result.order_id));
      setStatusMessage(result.message);
      setPaymentOrder(null);
      setPaymentMethod("");
    } catch (error) {
      setPaymentError(error.message);
    } finally {
      setPaymentRecording(false);
    }
  }

  return (
    <>
      <section className="page-heading">
        <div>
          <p className="eyebrow">Sales activity</p>
          <h1>Orders</h1>
          <p className="page-description">
            Review incoming orders, their current status, and recorded totals.
          </p>
        </div>
        <div className="record-count" aria-label={`${filteredOrders.length} displayed orders`}>
          <strong>{filteredOrders.length}</strong>
          <span>{filteredOrders.length === 1 ? "order" : "orders"}</span>
        </div>
      </section>

      <div className="orders-layout">
        {deleteMessage && (
          <p className="message success-message list-message" role="status">
            {deleteMessage}
          </p>
        )}
        <section className="panel list-panel" aria-labelledby="orders-list-heading">
          <div className="panel-heading">
            <p className="section-number">01</p>
            <div>
              <h2 id="orders-list-heading">Order records</h2>
              <p>Select an order to view its full information.</p>
            </div>
          </div>

          <div className="status-filters" aria-label="Filter orders by status">
            {[
              ["active", "Active"],
              ["all", "All"],
              ["pending", "Pending"],
              ["completed", "Completed"],
              ["cancelled", "Cancelled"],
            ].map(([value, label]) => (
              <button
                key={value}
                type="button"
                className={`filter-button${statusFilter === value ? " active" : ""}`}
                onClick={() => setStatusFilter(value)}
                aria-pressed={statusFilter === value}
              >
                {label}
              </button>
            ))}
            <select className="payment-filter" value={paymentFilter} onChange={(event) => setPaymentFilter(event.target.value)} aria-label="Filter orders by payment status"><option value="all">All payments</option><option value="unpaid">Unpaid orders</option><option value="paid">Paid orders</option></select>
          </div>

          {loading && <p className="state-message">Loading orders…</p>}

          {!loading && loadError && (
            <div className="state-message error-state">
              <strong>Orders could not be loaded.</strong>
              <span>{loadError}</span>
            </div>
          )}

          {!loading && !loadError && filteredOrders.length === 0 && (
            <div className="state-message empty-state">
              <strong>{orders.length === 0 ? "No orders yet." : "No orders match this filter."}</strong>
              <span>
                {orders.length === 0
                  ? "New orders will appear here when they are created."
                  : "Choose another status to see different orders."}
              </span>
            </div>
          )}

          {!loading && !loadError && filteredOrders.length > 0 && (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>Order</th>
                    <th>Customer</th>
                    <th>Order Items</th>
                    <th>Status</th>
                    <th>Payment</th>
                    <th>Method</th>
                    <th>Total</th>
                    <th>Created</th>
                    <th><span className="visually-hidden">Action</span></th>
                  </tr>
                </thead>
                <tbody>
                  {filteredOrders.map((order) => (
                    <tr key={order.order_id}>
                      <td data-label="Order">
                        <strong>{order.order_number}</strong>
                        <span className="record-id">ID #{order.order_id}</span>
                      </td>
                      <td data-label="Customer">{order.customer_name}</td>
                      <td data-label="Order Items">{order.item_summary}</td>
                      <td data-label="Status">
                        <span className={`status-badge status-${order.order_status}`}>
                          {formatStatus(order.order_status)}
                        </span>
                      </td>
                      <td data-label="Payment"><span className={`payment-badge payment-${order.payment_status}`}>{order.payment_status === "paid" ? "Paid" : "Unpaid"}</span></td>
                      <td data-label="Method">{paymentMethodLabel(order.payment_method)}</td>
                      <td data-label="Total" className="price-cell">
                        {formatAmount(order.total_amount)}
                      </td>
                      <td data-label="Created">{formatDate(order.created_at)}</td>
                      <td data-label="Action">
                        <button
                          type="button"
                          className="secondary-button"
                          onClick={() => handleViewOrder(order.order_id)}
                        >
                          View
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {(detailsLoading || detailsError || selectedOrder) && (
          <section className="panel details-panel" aria-live="polite">
            <div className="panel-heading">
              <p className="section-number">02</p>
              <div>
                <h2>Order details</h2>
                <p>Information for the selected order.</p>
              </div>
            </div>

            {detailsLoading && <p className="state-message">Loading order details…</p>}

            {!detailsLoading && detailsError && (
              <p className="message error-message details-message">{detailsError}</p>
            )}

            {!detailsLoading && selectedOrder && (
              <>
                <dl className="details-grid">
                  <div>
                    <dt>Order number</dt>
                    <dd>{selectedOrder.order_number}</dd>
                  </div>
                  <div>
                    <dt>Customer name</dt>
                    <dd>{selectedOrder.customer.name}</dd>
                  </div>
                  <div>
                    <dt>Phone number</dt>
                    <dd><a className="phone-link" href={`tel:${selectedOrder.customer.phone_number}`}>{selectedOrder.customer.phone_number}</a></dd>
                  </div>
                  <div>
                    <dt>Status</dt>
                    <dd>
                      <span className={`status-badge status-${selectedOrder.order_status}`}>
                        {formatStatus(selectedOrder.order_status)}
                      </span>
                    </dd>
                  </div>
                  <div>
                    <dt>Total amount</dt>
                    <dd className="detail-total">
                      {formatAmount(selectedOrder.total_amount)}
                    </dd>
                  </div>
                  <div><dt>Payment status</dt><dd><span className={`payment-badge payment-${selectedOrder.payment_status}`}>{selectedOrder.payment_status === "paid" ? "Paid" : "Unpaid"}</span></dd></div>
                  <div><dt>Payment method</dt><dd>{paymentMethodLabel(selectedOrder.payment_method)}</dd></div>
                  <div><dt>Paid at</dt><dd>{formatDate(selectedOrder.paid_at)}</dd></div>
                  {selectedOrder.mpesa_payment?.mpesa_receipt_number && <div><dt>M-Pesa receipt</dt><dd>{selectedOrder.mpesa_payment.mpesa_receipt_number}</dd></div>}
                  <div>
                    <dt>Created</dt>
                    <dd>{formatDate(selectedOrder.created_at)}</dd>
                  </div>
                  <div>
                    <dt>Last updated</dt>
                    <dd>{formatDate(selectedOrder.updated_at)}</dd>
                  </div>
                  <div className="detail-notes">
                    <dt>Notes</dt>
                    <dd>{selectedOrder.notes || "No notes for this order."}</dd>
                  </div>
                </dl>

                <section className="order-items-section" aria-labelledby="order-items-heading">
                  <h2 id="order-items-heading">Order Items</h2>
                  {selectedOrder.items.length === 0 ? (
                    <p className="state-message">No items are recorded for this order.</p>
                  ) : (
                    <div className="table-wrapper">
                      <table>
                        <thead><tr><th>Product</th><th>Quantity</th><th>Unit</th><th>Unit Price</th><th>Line Total</th></tr></thead>
                        <tbody>{selectedOrder.items.map((item) => (
                          <tr key={item.order_item_id}>
                            <td data-label="Product"><strong>{item.product_name}</strong></td>
                            <td data-label="Quantity">{quantityWithUnit(item.quantity, item.unit_name)}</td>
                            <td data-label="Unit">{item.unit_name}</td>
                            <td data-label="Unit Price" className="price-cell">{formatAmount(item.unit_price)}</td>
                            <td data-label="Line Total" className="price-cell">{formatAmount(item.line_total)}</td>
                          </tr>
                        ))}</tbody>
                      </table>
                    </div>
                  )}
                  <p className="order-items-total">Order Total: <strong>{formatAmount(selectedOrder.total_amount)}</strong></p>
                </section>

                <div className="details-actions">
                  {selectedOrder.payment_status === "unpaid" && selectedOrder.order_status !== "cancelled" && <button type="button" className="secondary-button" onClick={() => { setPaymentOrder(selectedOrder); setPaymentMethod(""); setPaymentError(""); }}>Mark as Paid</button>}
                  {selectedOrder.order_status === "pending" && (
                    <button
                      type="button"
                      onClick={handleMarkCompleted}
                      disabled={statusUpdating}
                    >
                      {statusUpdating ? "Updating status…" : "Mark as Completed"}
                    </button>
                  )}
                  {selectedOrder.order_status === "cancelled" && (
                    <button
                      type="button"
                      className="danger-button"
                      onClick={() => {
                        setDeleteError("");
                        setOrderToDelete(selectedOrder);
                      }}
                    >
                      Delete
                    </button>
                  )}
                  {statusError && (
                    <p className="message error-message">{statusError}</p>
                  )}
                  {statusMessage && (
                    <p className="message success-message">{statusMessage}</p>
                  )}
                </div>
              </>
            )}
          </section>
        )}
      </div>

      {orderToDelete && (
        <div className="modal-backdrop" role="presentation">
          <div
            className="confirmation-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-order-heading"
          >
            <p className="eyebrow">Permanent action</p>
            <h2 id="delete-order-heading">
              Delete cancelled order {orderToDelete.order_number}?
            </h2>
            <p>This will permanently remove the order and cannot be undone.</p>
            {deleteError && <p className="message error-message">{deleteError}</p>}
            <div className="dialog-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={() => setOrderToDelete(null)}
                disabled={deleting}
              >
                Cancel
              </button>
              <button
                type="button"
                className="danger-button"
                onClick={handleDeleteOrder}
                disabled={deleting}
              >
                {deleting ? "Deleting…" : "Delete Order"}
              </button>
            </div>
          </div>
        </div>
      )}

      {paymentOrder && <div className="modal-backdrop" role="presentation"><form className="confirmation-dialog" role="dialog" aria-modal="true" aria-labelledby="record-payment-heading" onSubmit={handleRecordPayment}><p className="eyebrow">Record Payment</p><h2 id="record-payment-heading">Order {paymentOrder.order_number}</h2><p>Amount: <strong>{formatAmount(paymentOrder.total_amount)}</strong></p><label>Payment Method<select value={paymentMethod} onChange={(event) => { setPaymentMethod(event.target.value); setPaymentError(""); }} required><option value="">Select payment method</option><option value="cash">Cash</option><option value="bank_transfer">Bank Transfer</option></select></label>{paymentError && <p className="message error-message">{paymentError}</p>}<div className="dialog-actions"><button type="button" className="secondary-button" onClick={() => setPaymentOrder(null)} disabled={paymentRecording}>Cancel</button><button type="submit" disabled={paymentRecording}>{paymentRecording ? "Recording…" : "Confirm Payment"}</button></div></form></div>}
    </>
  );
}

export default OrdersPage;
