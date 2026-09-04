const ORDERS_URL = "/api/orders";

async function readResponse(response) {
  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(data?.error || "The order request failed. Please try again.");
  }

  return data;
}

export async function getOrders() {
  const response = await apiFetch(ORDERS_URL);
  return readResponse(response);
}

export async function getOrder(orderId) {
  const response = await apiFetch(`${ORDERS_URL}/${orderId}`);
  return readResponse(response);
}

export async function createOrder(order) {
  const response = await apiFetch(ORDERS_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(order),
  });

  return readResponse(response);
}

export async function addOrderItem(orderId, item) {
  const response = await apiFetch(`${ORDERS_URL}/${orderId}/items`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(item),
  });

  return readResponse(response);
}

export async function updateOrder(orderId, updates) {
  const response = await apiFetch(`${ORDERS_URL}/${orderId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(updates),
  });

  return readResponse(response);
}

export async function deleteOrder(orderId) {
  const response = await apiFetch(`${ORDERS_URL}/${orderId}`, {
    method: "DELETE",
  });

  return readResponse(response);
}

export async function recordOrderPayment(orderId, paymentMethod) {
  const response = await apiFetch(`${ORDERS_URL}/${orderId}/payment`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ payment_status: "paid", payment_method: paymentMethod }),
  });
  return readResponse(response);
}
import { apiFetch } from "./config.js";
