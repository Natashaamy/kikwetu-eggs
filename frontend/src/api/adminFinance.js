import { apiFetch } from './config.js';
export async function adminRequest(path, method = 'GET', body) {
  const response = await apiFetch(`/api/admin/${path}`, { method, headers: { 'Content-Type': 'application/json' }, ...(body ? { body: JSON.stringify(body) } : {}) });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Unable to complete your request');
  return data;
}
