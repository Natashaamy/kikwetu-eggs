import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { adminRequest } from '../api/adminFinance.js';
import { money, nairobiToday } from '../utils/format.js';
import TemporaryMessage from '../components/TemporaryMessage.jsx';

const blank = (category = 'feed') => ({ category, item_name: '', quantity: '', unit: category === 'feed' ? 'kg' : 'bottles', unit_price: '', purchase_date: nairobiToday(), notes: '', submission_key: crypto.randomUUID() });
export default function FarmExpensesPage() {
  const [params] = useSearchParams();
  const [form, setForm] = useState(() => blank(params.get('category') === 'medicine' ? 'medicine' : 'feed'));
  const [editing, setEditing] = useState(null);
  const [data, setData] = useState(null);
  const [filter, setFilter] = useState({ category: '', from: '', to: '' });
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const saving = useRef(false);
  async function load() { setData(await adminRequest(`expenses?${new URLSearchParams(filter)}`)); }
  useEffect(() => { let ignore = false; adminRequest(`expenses?${new URLSearchParams(filter)}`).then(result => { if (!ignore) setData(result); }).catch(e => { if (!ignore) setError(e.message); }); return () => { ignore = true; }; }, [filter]);
  async function save(e) {
    e.preventDefault(); if (saving.current) return;
    saving.current = true; setBusy(true); setMessage(''); setError('');
    try {
      const result = await adminRequest(editing ? `expenses/${editing}` : 'expenses', editing ? 'PUT' : 'POST', form);
      setMessage(result.message); setForm(blank(form.category)); setEditing(null); await load();
    } catch (err) { setError(err.message); }
    finally { saving.current = false; setBusy(false); }
  }
  async function remove(row) {
    if (!window.confirm(`Delete ${row.item_name} expense? Its audit history will be retained.`)) return;
    setBusy(true); setMessage(''); setError('');
    try { const result = await adminRequest(`expenses/${row.id}`, 'DELETE'); setMessage(result.message); if (editing === row.id) { setEditing(null); setForm(blank()); } await load(); }
    catch (err) { setError(err.message); } finally { setBusy(false); }
  }
  function field(key, label, type = 'text', extra = {}) { return <label>{label}<input {...extra} type={type} value={form[key]} onChange={e => setForm({ ...form, [key]: e.target.value })} required /></label>; }
  return <><section className="page-heading"><div><h1>Farm Expenses</h1><p>Record chicken feed and medicine purchases.</p></div></section>
    {message && <TemporaryMessage className="success-message">{message}</TemporaryMessage>}{error && <TemporaryMessage className="error-message" role="alert">{error}</TemporaryMessage>}
    {data && <section className="panel finance-panel table-wrapper expense-totals"><table><caption>Saved expenses this week and month (EAT)</caption><thead><tr><th>Expense</th><th>This Week</th><th>This Month</th></tr></thead><tbody>{[['Chicken Feed', 'feed'], ['Chicken Medicine', 'medicine'], ['Total', 'total']].map(([label, key]) => <tr key={key}><th>{label}</th><td>{money.format(data.week[key])}</td><td>{money.format(data.month[key])}</td></tr>)}</tbody></table></section>}
    <section className="panel finance-panel"><h2>{editing ? 'Edit Expense' : 'Add Expense'}</h2><form onSubmit={save} className="expense-form"><label>Category<select value={form.category} onChange={e => setForm({ ...form, category: e.target.value, unit: e.target.value === 'feed' ? 'kg' : 'bottles' })}><option value="feed">Chicken Feed</option><option value="medicine">Chicken Medicine</option></select></label>
      {field('item_name', form.category === 'feed' ? 'Feed Type' : 'Medicine Name', 'text', { maxLength: 150, list: form.category === 'feed' ? 'feed-types' : undefined })}<datalist id="feed-types"><option>Chick Mash</option><option>Growers Mash</option><option>Layers Mash</option></datalist>
      {field('quantity', form.category === 'feed' ? 'Quantity (kg)' : 'Quantity', 'number', { min: '.001', max: '1000000', step: '.001' })}
      {form.category === 'medicine' && field('unit', 'Unit (bottles, packs, tablets…)')}
      {field('unit_price', form.category === 'feed' ? 'Price per kg (KES)' : 'Price per Unit (KES)', 'number', { min: '0', max: '100000000', step: '.01' })}
      {field('purchase_date', 'Purchase Date', 'date', { max: nairobiToday() })}<label>Notes (optional)<textarea value={form.notes} maxLength={2000} onChange={e => setForm({ ...form, notes: e.target.value })} /></label>
      <output aria-live="polite">Total Cost: <strong>{money.format(Number(form.quantity || 0) * Number(form.unit_price || 0))}</strong></output><div><button disabled={busy}>{busy ? 'Saving…' : 'Save Expense'}</button>{editing && <button type="button" className="secondary-button" onClick={() => { setEditing(null); setForm(blank()); }}>Cancel Edit</button>}</div>
    </form></section>
    <section className="panel finance-panel" id="history"><h2>Expense History</h2><div className="finance-filters"><label>Category<select value={filter.category} onChange={e => setFilter({ ...filter, category: e.target.value })}><option value="">All</option><option value="feed">Chicken Feed</option><option value="medicine">Chicken Medicine</option></select></label>{['from', 'to'].map(key => <label key={key}>{key === 'from' ? 'From' : 'To'}<input type="date" value={filter[key]} onChange={e => setFilter({ ...filter, [key]: e.target.value })} /></label>)}</div>
      <div className="table-wrapper"><table><thead><tr>{['Date', 'Category', 'Item Name', 'Quantity', 'Unit Price', 'Total Amount', 'Actions'].map(h => <th key={h}>{h}</th>)}</tr></thead><tbody>{data?.expenses.map(row => <tr key={row.id}><td data-label="Date">{row.purchase_date}</td><td data-label="Category">{row.category}</td><td data-label="Item Name">{row.item_name}</td><td data-label="Quantity">{row.quantity} {row.unit}</td><td data-label="Unit Price">{money.format(row.unit_price)}</td><td data-label="Total Amount">{money.format(row.total_amount)}</td><td data-label="Actions"><button disabled={busy} onClick={() => { setEditing(row.id); setForm(row); window.scrollTo({ top: 0 }); }}>Edit</button> <button className="danger-button" disabled={busy} onClick={() => remove(row)}>Delete</button></td></tr>)}</tbody></table>{data?.expenses.length === 0 && <p>No expenses in this period.</p>}</div>
    </section></>;
}
