import { useEffect, useMemo, useState } from "react";
import { deleteAdminCustomer, getAdminCustomer, getAdminCustomers, updateAdminCustomerStatus } from "../api/adminCustomers.js";

const money = new Intl.NumberFormat("en-KE", { style: "currency", currency: "KES", minimumFractionDigits: 0 });
const dateFormat = new Intl.DateTimeFormat("en-KE", { dateStyle: "medium" });
const formatDate = (value) => { if (!value) return "—"; const date = new Date(`${value.replace(" ", "T")}Z`); return Number.isNaN(date.getTime()) ? value : dateFormat.format(date); };
const title = (value) => value ? value.charAt(0).toUpperCase() + value.slice(1) : "—";

export default function CustomersPage() {
  const [customers, setCustomers] = useState([]);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [details, setDetails] = useState(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [confirmation, setConfirmation] = useState(null);
  const [acting, setActing] = useState(false);
  const [actionError, setActionError] = useState("");

  useEffect(() => { getAdminCustomers().then((data) => setCustomers(data.customers || [])).catch(() => setError("Customer accounts could not be loaded.")).finally(() => setLoading(false)); }, []);
  const summary = useMemo(() => ({ total: customers.length, active: customers.filter((c) => c.is_active).length, inactive: customers.filter((c) => !c.is_active).length }), [customers]);
  const visible = useMemo(() => { const term = search.trim().toLowerCase(); return customers.filter((customer) => (!term || customer.name.toLowerCase().includes(term) || customer.phone_number.toLowerCase().includes(term)) && (statusFilter === "all" || (statusFilter === "active") === Boolean(customer.is_active))); }, [customers, search, statusFilter]);

  async function viewCustomer(customerId) { setDetailsLoading(true); setActionError(""); try { setDetails(await getAdminCustomer(customerId)); } catch { setActionError("Customer details could not be loaded."); } finally { setDetailsLoading(false); } }
  function updateLocal(customer) { setCustomers((current) => current.map((item) => item.customer_id === customer.customer_id ? { ...item, ...customer } : item)); setDetails((current) => current?.customer.customer_id === customer.customer_id ? { ...current, customer: { ...current.customer, ...customer } } : current); }
  async function confirmAction() {
    if (!confirmation) return; setActing(true); setActionError("");
    try {
      if (confirmation.type === "delete") {
        const result = await deleteAdminCustomer(confirmation.customer.customer_id);
        setCustomers((current) => current.filter((item) => item.customer_id !== confirmation.customer.customer_id));
        if (details?.customer.customer_id === confirmation.customer.customer_id) setDetails(null);
        setMessage(result.message);
      } else {
        const result = await updateAdminCustomerStatus(confirmation.customer.customer_id, confirmation.type === "reactivate");
        updateLocal(result.customer); setMessage(result.message);
      }
      setConfirmation(null);
    } catch (requestError) { setActionError(requestError.message); }
    finally { setActing(false); }
  }

  function actionButtons(customer) { return <div className="admin-customer-actions"><button type="button" className="secondary-button" onClick={() => viewCustomer(customer.customer_id)}>View Details</button><button type="button" className={customer.is_active ? "deactivate-button" : "reactivate-button"} onClick={() => { setActionError(""); setConfirmation({ type: customer.is_active ? "deactivate" : "reactivate", customer }); }}>{customer.is_active ? "Deactivate" : "Reactivate"}</button><button type="button" className="delete-text-button" onClick={() => { setActionError(""); setConfirmation({ type: "delete", customer }); }}>Delete Permanently</button></div>; }

  return <>
    <section className="page-heading"><div><p className="eyebrow">Account management</p><h1>Customers</h1><p className="page-description">Manage customer accounts and activity.</p></div></section>
    <section className="admin-summary-grid"><article><span>Total Customers</span><strong>{summary.total}</strong></article><article className="summary-active"><span>Active Customers</span><strong>{summary.active}</strong></article><article className="summary-inactive"><span>Deactivated</span><strong>{summary.inactive}</strong></article></section>
    {message && <p className="message success-message list-message" role="status">{message}</p>}{actionError && !confirmation && <p className="message error-message list-message">{actionError}</p>}
    <section className="panel admin-list-panel"><div className="admin-toolbar"><label className="search-field">Search customers<input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Name or phone number" /></label><label>Account status<select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="all">All</option><option value="active">Active</option><option value="inactive">Deactivated</option></select></label></div>
      {loading && <p className="state-message">Loading customers…</p>}{error && <div className="state-message error-state"><strong>Customers unavailable.</strong><span>{error}</span></div>}{!loading && !error && visible.length === 0 && <div className="state-message empty-state"><strong>No customers found.</strong><span>Try changing the search or status filter.</span></div>}
      {!loading && !error && visible.length > 0 && <div className="admin-customer-grid">{visible.map((customer) => <article className="admin-customer-card" key={customer.customer_id}><div className="customer-card-identity"><div className="mini-avatar">{customer.name.charAt(0).toUpperCase()}</div><div><h2>{customer.name}</h2><a href={`tel:${customer.phone_number}`}>{customer.phone_number}</a></div><span className={`status-badge ${customer.is_active ? "active" : "inactive"}`}>{customer.is_active ? "Active" : "Deactivated"}</span></div><dl><div><dt>Orders</dt><dd>{customer.total_orders}</dd></div><div><dt>Total spent</dt><dd>{money.format(customer.total_spent)}</dd></div><div><dt>Joined</dt><dd>{formatDate(customer.created_at)}</dd></div></dl>{actionButtons(customer)}</article>)}</div>}
    </section>

    {(details || detailsLoading) && <div className="modal-backdrop" role="presentation"><div className="confirmation-dialog customer-detail-modal" role="dialog" aria-modal="true" aria-labelledby="customer-detail-heading"><div className="dialog-title-row"><div><p className="eyebrow">Customer details</p><h2 id="customer-detail-heading">{details?.customer.name || "Loading…"}</h2></div><button type="button" className="dialog-close" aria-label="Close" onClick={() => setDetails(null)}>×</button></div>{detailsLoading ? <p className="state-message">Loading details…</p> : details && <><div className="customer-detail-profile"><div className="mini-avatar large">{details.customer.name.charAt(0).toUpperCase()}</div><div><strong>{details.customer.name}</strong><a href={`tel:${details.customer.phone_number}`}>{details.customer.phone_number}</a><span className={`status-badge ${details.customer.is_active ? "active" : "inactive"}`}>{details.customer.is_active ? "Active" : "Deactivated"}</span></div><small>Joined {formatDate(details.customer.created_at)}</small></div><section className="customer-activity-grid"><div><span>Total Orders</span><strong>{details.statistics.total_orders}</strong></div><div><span>Completed</span><strong>{details.statistics.completed_orders}</strong></div><div><span>Processing</span><strong>{details.statistics.processing_orders}</strong></div><div><span>Cancelled</span><strong>{details.statistics.cancelled_orders}</strong></div><div><span>Total Spent</span><strong>{money.format(details.statistics.total_spent)}</strong></div></section><div className="recent-customer-orders"><h3>Recent Orders</h3>{details.orders.length === 0 ? <p>No orders yet.</p> : details.orders.slice(0, 5).map((order) => <div key={order.order_number}><strong>{order.order_number}</strong><span>{formatDate(order.created_at)}</span><b>{money.format(order.total_amount)}</b><span className={`status-badge status-${order.order_status}`}>{title(order.order_status)}</span><span className={`payment-badge payment-${order.payment_status}`}>{title(order.payment_status)}</span></div>)}</div>{actionButtons(details.customer)}</>}</div></div>}

    {confirmation && <div className="modal-backdrop" role="presentation"><div className="confirmation-dialog" role="dialog" aria-modal="true"><p className="eyebrow">Account action</p><h2>{confirmation.type === "delete" ? "Permanently Delete Customer?" : confirmation.type === "deactivate" ? "Deactivate Customer?" : "Reactivate Customer?"}</h2><p>{confirmation.type === "delete" ? "This action cannot be undone. It is available only when the customer has no order or payment history." : confirmation.type === "deactivate" ? `${confirmation.customer.name} will no longer be able to sign in or access their account. Their business history will remain available.` : `${confirmation.customer.name} will regain access to their account.`}</p>{actionError && <p className="message error-message">{actionError}</p>}<div className="dialog-actions"><button type="button" className="secondary-button" onClick={() => setConfirmation(null)} disabled={acting}>{confirmation.type === "deactivate" ? "Keep Active" : "Cancel"}</button><button type="button" className={confirmation.type === "delete" ? "danger-button" : ""} onClick={confirmAction} disabled={acting}>{acting ? "Updating…" : confirmation.type === "delete" ? "Delete Permanently" : confirmation.type === "deactivate" ? "Deactivate Account" : "Reactivate"}</button></div></div></div>}
  </>;
}
