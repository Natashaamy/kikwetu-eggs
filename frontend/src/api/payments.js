const MPESA_URL = "/api/payments/mpesa";

async function readResponse(response) {
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error(data?.error || "The M-Pesa request could not be completed.");
    error.details = data;
    throw error;
  }
  return data;
}

export async function sendMpesaPrompt(orderId) {
  const storageKey = `mpesa-attempt:${orderId}`;
  const requestKey = sessionStorage.getItem(storageKey) || crypto.randomUUID();
  sessionStorage.setItem(storageKey, requestKey);
  const response = await apiFetch(`${MPESA_URL}/stk-push`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ order_id: orderId, request_key: requestKey }),
  });
  const result = await readResponse(response);
  if (result.payment_status === 'rejected' || result.payment_status === 'resolved') {
    sessionStorage.removeItem(storageKey);
    throw new Error('The previous attempt is finished. Refresh the order before trying again.');
  }
  if (result.payment_status === 'unknown' || result.payment_status === 'reserved') {
    throw new Error('Payment verification is unresolved. Do not send another payment; contact support.');
  }
  return result;
}

export async function getMpesaPaymentStatus(checkoutRequestId) {
  const response = await apiFetch(`${MPESA_URL}/status/${encodeURIComponent(checkoutRequestId)}`);
  const result = await readResponse(response);
  if (['failed', 'cancelled', 'successful'].includes(result.status)) {
    sessionStorage.removeItem(`mpesa-attempt:${result.order_id}`);
  }
  return result;
}
import { apiFetch } from "./config.js";
