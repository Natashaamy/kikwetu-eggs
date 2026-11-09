export const money = new Intl.NumberFormat('en-KE', { style: 'currency', currency: 'KES', currencyDisplay: 'code', minimumFractionDigits: 2 });
export function formatDate(value) {
  if (!value) return '—';
  const text = String(value).replace(' ', 'T');
  const date = new Date(/(Z|[+-]\d\d:\d\d)$/.test(text) ? text : `${text}Z`);
  if (Number.isNaN(date.getTime())) return '—';
  return `${new Intl.DateTimeFormat('en-KE', { timeZone: 'Africa/Nairobi', year: 'numeric', month: 'long', day: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true }).format(date)} EAT`;
}
export function nairobiToday() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Africa/Nairobi', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
}
