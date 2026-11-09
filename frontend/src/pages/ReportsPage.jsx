import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { adminRequest } from '../api/adminFinance.js';
import { money } from '../utils/format.js';

export default function ReportsPage() {
  const [period, setPeriod] = useState('month');
  const [range, setRange] = useState({ from: '', to: '' });
  const [report, setReport] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    setReport(null); setError('');
    if (period === 'custom' && (!range.from || !range.to)) return;
    adminRequest(`reports/summary?${new URLSearchParams({ period, ...range })}`).then(data => { if (!cancelled) setReport(data); }).catch(e => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, [period, range]);
  const labels = [['Paid Orders', 'paid_orders_amount'], ['Unpaid Orders', 'unpaid_orders_amount'], ['Feed Expenses', 'feed_expenses'], ['Medicine Expenses', 'medicine_expenses'], ['Total Expenses', 'total_expenses'], ['Net Cash Balance', 'net_cash_balance']];
  return <><section className="page-heading"><div><h1>Financial Reports</h1><p>Overview of orders, payments, and farm expenses.</p></div></section>
    <section className="panel finance-panel finance-filters"><label>Reporting period<select value={period} onChange={e => setPeriod(e.target.value)}><option value="week">This Week</option><option value="month">This Month</option><option value="custom">Custom Date Range</option></select></label>{period === 'custom' && <>{['from', 'to'].map(key => <label key={key}>{key === 'from' ? 'From' : 'To'}<input type="date" value={range[key]} onChange={e => setRange({ ...range, [key]: e.target.value })} /></label>)}</>}</section>
    {error && <p role="alert" className="message error-message">{error}</p>}
    {report && <><p>{report.period.from} – {report.period.to} · Africa/Nairobi</p><section className="stats-grid">{labels.map(([label, key]) => <article className="stat-card" key={key}><span>{label}</span><strong>{money.format(report.summary[key])}</strong></article>)}</section>
      <section className="panel finance-panel"><h2>About these figures</h2><p>Paid orders show receipts less refunds in this period for valid orders, including partial payments. Unpaid orders show the remaining balance of valid orders created in this period.</p><p>Confirmed payments received: <strong>{money.format(report.summary.confirmed_payments_received)}</strong>. Refunds recorded: <strong>{money.format(report.summary.refunds_paid || 0)}</strong>. Net Cash Balance subtracts refunds, feed and medicine expenses from these receipts. This is a simplified cash balance, not accounting profit; other operating costs are not included.</p></section></>}
    <nav className="finance-actions" aria-label="Expense actions"><Link className="primary-link" to="/admin/expenses?category=feed">Add Feed Expense</Link><Link className="primary-link" to="/admin/expenses?category=medicine">Add Medicine Expense</Link><Link to="/admin/expenses#history">View Expense History</Link></nav>
  </>;
}
