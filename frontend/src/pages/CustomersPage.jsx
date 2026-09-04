import { useEffect, useMemo, useState } from "react";

import {
  deleteAdminCustomer,
  getAdminCustomer,
  getAdminCustomers,
} from "../api/adminCustomers.js";

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
  if (!date) return "No orders yet";
  const parsedDate = new Date(`${date.replace(" ", "T")}Z`);
  return Number.isNaN(parsedDate.getTime()) ? date : dateFormatter.format(parsedDate);
}

function formatStatus(status) {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

export default function CustomersPage() {
  const [customers, setCustomers] = useState([]);
  const [search, setSearch] = useState("");
  const [orderFilter, setOrderFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [detailsError, setDetailsError] = useState("");
  const [customerToDelete, setCustomerToDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let ignoreResult = false;
    getAdminCustomers()
      .then((data) => {
        if (!ignoreResult) setCustomers(data.customers || []);
      })
      .catch(() => {
        if (!ignoreResult) setError("Customer accounts could not be loaded. Please try again.");
      })
      .finally(() => {
        if (!ignoreResult) setLoading(false);
      });
    return () => { ignoreResult = true; };
  }, []);

  const visibleCustomers = useMemo(() => {
    const term = search.trim().toLowerCase();
    return customers.filter((customer) => {
      const matchesSearch = !term
        || customer.name.toLowerCase().includes(term)
        || customer.phone_number.toLowerCase().includes(term);
      const matchesOrders = orderFilter === "all"
        || (orderFilter === "with" && customer.total_orders > 0)
        || (orderFilter === "without" && customer.total_orders === 0);
      return matchesSearch && matchesOrders;
    });
  }, [customers, orderFilter, search]);

  async function handleView(customerId) {
    setDetailsLoading(true);
    setDetailsError("");
    setSelected(null);
    try {
      setSelected(await getAdminCustomer(customerId));
    } catch {
      setDetailsError("Customer details could not be loaded. Please try again.");
    } finally {
      setDetailsLoading(false);
    }
  }

  async function handleDelete() {
    if (!customerToDelete) return;
    setDeleting(true);
    setDeleteError("");
    try {
      const result = await deleteAdminCustomer(customerToDelete.customer_id);
      setCustomers((current) => current.filter(
        (customer) => customer.customer_id !== customerToDelete.customer_id,
      ));
      if (selected?.customer.customer_id === customerToDelete.customer_id) setSelected(null);
      setCustomerToDelete(null);
      setMessage(result.message);
    } catch (requestError) {
      setDeleteError(requestError.message);
    } finally {
      setDeleting(false);
    }
  }

  return <>
    <section className="page-heading">
      <div>
        <p className="eyebrow">Account management</p>
        <h1>Customers</h1>
        <p className="page-description">Review registered accounts and their order activity.</p>
      </div>
      <div className="record-count"><strong>{visibleCustomers.length}</strong><span>customers</span></div>
    </section>

    {message && <p className="message success-message list-message" role="status">{message}</p>}

    <section className="panel" aria-labelledby="customer-list-heading">
      <div className="panel-heading"><p className="section-number">01</p><div><h2 id="customer-list-heading">Customer accounts</h2><p>Search by name or phone number.</p></div></div>
      <div className="customer-toolbar">
        <label>Search customers<input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Name or phone number" /></label>
        <label>Order activity<select value={orderFilter} onChange={(event) => setOrderFilter(event.target.value)}><option value="all">All customers</option><option value="with">With orders</option><option value="without">Without orders</option></select></label>
      </div>

      {loading && <p className="state-message">Loading customers…</p>}
      {!loading && error && <div className="state-message error-state"><strong>Customers unavailable.</strong><span>{error}</span></div>}
      {!loading && !error && visibleCustomers.length === 0 && <div className="state-message empty-state"><strong>No customers found.</strong><span>Try changing the search or order filter.</span></div>}
      {!loading && !error && visibleCustomers.length > 0 && <div className="table-wrapper"><table><thead><tr><th>Customer</th><th>Phone</th><th>Orders</th><th>Completed</th><th>Total Spent</th><th>Last Order</th><th>Account Created</th><th><span className="visually-hidden">Actions</span></th></tr></thead><tbody>
        {visibleCustomers.map((customer) => <tr key={customer.customer_id}>
          <td data-label="Customer"><strong>{customer.name}</strong></td>
          <td data-label="Phone"><a className="phone-link" href={`tel:${customer.phone_number}`}>{customer.phone_number}</a></td>
          <td data-label="Orders">{customer.total_orders}</td>
          <td data-label="Completed">{customer.completed_orders}</td>
          <td data-label="Total Spent" className="price-cell">{formatAmount(customer.total_spent)}</td>
          <td data-label="Last Order">{formatDate(customer.last_order_date)}</td>
          <td data-label="Created">{formatDate(customer.created_at)}</td>
          <td data-label="Actions"><div className="row-actions"><button type="button" className="secondary-button" onClick={() => handleView(customer.customer_id)}>View</button><button type="button" className="danger-button" onClick={() => { setDeleteError(""); setCustomerToDelete(customer); }}>Delete</button></div></td>
        </tr>)}
      </tbody></table></div>}
    </section>

    {(detailsLoading || detailsError || selected) && <section className="panel customer-details-panel" aria-live="polite">
      <div className="panel-heading"><p className="section-number">02</p><div><h2>Customer details</h2><p>Profile, order statistics, and history.</p></div></div>
      {detailsLoading && <p className="state-message">Loading customer details…</p>}
      {!detailsLoading && detailsError && <p className="message error-message details-message">{detailsError}</p>}
      {!detailsLoading && selected && <>
        <dl className="details-grid customer-profile-grid">
          <div><dt>Customer name</dt><dd>{selected.customer.name}</dd></div>
          <div><dt>Phone number</dt><dd>{selected.customer.phone_number}</dd></div>
          <div><dt>Account created</dt><dd>{formatDate(selected.customer.created_at)}</dd></div>
          <div><dt>Total orders</dt><dd>{selected.statistics.total_orders}</dd></div>
          <div><dt>Pending</dt><dd>{selected.statistics.pending_orders}</dd></div>
          <div><dt>Completed</dt><dd>{selected.statistics.completed_orders}</dd></div>
          <div><dt>Cancelled</dt><dd>{selected.statistics.cancelled_orders}</dd></div>
          <div><dt>Total spent</dt><dd className="detail-total">{formatAmount(selected.statistics.total_spent)}</dd></div>
          <div><dt>Most recent order</dt><dd>{formatDate(selected.statistics.most_recent_order)}</dd></div>
        </dl>
        <div className="customer-order-history"><h2>Order history</h2>
          {selected.orders.length === 0 ? <p className="state-message">This customer has no orders.</p> : <div className="table-wrapper"><table><thead><tr><th>Order Number</th><th>Status</th><th>Total</th><th>Date</th></tr></thead><tbody>{selected.orders.map((order) => <tr key={order.order_number}><td data-label="Order"><strong>{order.order_number}</strong></td><td data-label="Status"><span className={`status-badge status-${order.order_status}`}>{formatStatus(order.order_status)}</span></td><td data-label="Total" className="price-cell">{formatAmount(order.total_amount)}</td><td data-label="Date">{formatDate(order.created_at)}</td></tr>)}</tbody></table></div>}
        </div>
      </>}
    </section>}

    {customerToDelete && <div className="modal-backdrop" role="presentation"><div className="confirmation-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-customer-heading"><p className="eyebrow">Permanent action</p><h2 id="delete-customer-heading">Delete customer account “{customerToDelete.name}”?</h2><p>This will permanently delete:</p><ul className="destructive-summary"><li>1 customer account</li><li>{customerToDelete.total_orders} {customerToDelete.total_orders === 1 ? "order" : "orders"}</li><li>{customerToDelete.order_items_count} {customerToDelete.order_items_count === 1 ? "order item" : "order items"}</li></ul><p>This action cannot be undone.</p>{deleteError && <p className="message error-message">{deleteError}</p>}<div className="dialog-actions"><button type="button" className="secondary-button" onClick={() => setCustomerToDelete(null)} disabled={deleting}>Cancel</button><button type="button" className="danger-button" onClick={handleDelete} disabled={deleting}>{deleting ? "Deleting…" : "Delete Customer"}</button></div></div></div>}
  </>;
}
