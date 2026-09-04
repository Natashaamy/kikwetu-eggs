const CUSTOMER_PORTAL_URL = "/api/customer";

async function get(path) {
  const response = await fetch(`${CUSTOMER_PORTAL_URL}${path}`);
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.error || "Customer information could not be loaded.");
  return data;
}

export const getCustomerDashboard = () => get("/dashboard");
export const getCustomerOrders = () => get("/orders");
export const getCustomerProfile = () => get("/profile");
export async function cancelCustomerOrder(orderId) {
  const response = await fetch(`${CUSTOMER_PORTAL_URL}/orders/${orderId}/cancel`, { method: "PATCH" });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.error || "Order cancellation failed.");
  return data;
}
