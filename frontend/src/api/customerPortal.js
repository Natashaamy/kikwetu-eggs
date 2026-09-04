const CUSTOMER_PORTAL_URL = "/api/customer";

async function get(path) {
  const response = await apiFetch(`${CUSTOMER_PORTAL_URL}${path}`);
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.error || "Customer information could not be loaded.");
  return data;
}

export const getCustomerDashboard = () => get("/dashboard");
export const getCustomerOrders = () => get("/orders");
export const getCustomerProfile = () => get("/profile");
export const getCustomerOrder = (orderId) => get(`/orders/${orderId}`);
export async function updateCustomerOrder(orderId, order) {
  const response = await apiFetch(`${CUSTOMER_PORTAL_URL}/orders/${orderId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(order),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.error || "Order update failed.");
  return data;
}
export async function updateCustomerProfile(profile) {
  const response = await apiFetch(`${CUSTOMER_PORTAL_URL}/profile`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.error || "Profile update failed.");
  return data;
}
export async function selectCashPayment(orderId) {
  const response = await apiFetch(`${CUSTOMER_PORTAL_URL}/orders/${orderId}/payment-method`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ payment_method: "cash" }),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.error || "Cash payment could not be selected.");
  return data;
}
export async function cancelCustomerOrder(orderId) {
  const response = await apiFetch(`${CUSTOMER_PORTAL_URL}/orders/${orderId}/cancel`, { method: "PATCH" });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.error || "Order cancellation failed.");
  return data;
}
import { apiFetch } from "./config.js";
