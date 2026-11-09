import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { adminRequest } from '../api/adminFinance.js';
import { formatDate } from '../utils/format.js';
export default function AdminNotifications() {
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState('');
  async function refresh() { try { setData(await adminRequest('notifications')); setError(''); } catch (e) { setError(e.message); } }
  useEffect(() => { let active = true; const load = () => adminRequest('notifications').then(d => { if (active) { setData(d); setError(''); } }).catch(e => { if (active) setError(e.message); }); load(); const id = setInterval(load, 30000); return () => { active = false; clearInterval(id); }; }, []);
  async function read(id) { try { await adminRequest(id ? `notifications/${id}/read` : 'notifications/read-all', 'PATCH'); await refresh(); } catch (e) { setError(e.message); } }
  async function older() { try { const next = await adminRequest(`notifications?before=${data.next_cursor}`); setData({ ...next, notifications: [...data.notifications, ...next.notifications] }); } catch (e) { setError(e.message); } }
  return <section className="admin-notifications"><button type="button" aria-expanded={open} onClick={() => setOpen(!open)}><span aria-hidden="true">♧</span> Notifications ({data?.unread_count || 0})</button>{open && <section className="panel notification-panel" aria-label="Admin notifications"><h2>Notifications</h2>{error && <p role="alert">{error}</p>}<button type="button" className="secondary-button" onClick={() => read()}>Mark all as read</button>{data?.notifications.map(n => <article className={n.read_at ? 'notification-read' : ''} key={n.id}><strong>{n.title}</strong><p>{n.description}</p><time>{formatDate(n.created_at)}</time><div>{!n.read_at && <button type="button" onClick={() => read(n.id)}>Mark as read</button>}{n.order_id && <Link to={`/admin/orders?order=${n.order_id}`} onClick={() => setOpen(false)}>Open order</Link>}</div></article>)}{data?.notifications.length === 0 && <p>No notifications yet.</p>}{data?.next_cursor && <button type="button" onClick={older}>View older notifications</button>}</section>}</section>;
}
