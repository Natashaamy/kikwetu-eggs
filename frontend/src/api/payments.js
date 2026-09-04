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
  const response = await apiFetch(`${MPESA_URL}/stk-push`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ order_id: orderId }),
  });
  return readResponse(response);
}

export async function getMpesaPaymentStatus(checkoutRequestId) {
  const response = await apiFetch(`${MPESA_URL}/status/${encodeURIComponent(checkoutRequestId)}`);
  return readResponse(response);
}
import { apiFetch } from "./config.js";
