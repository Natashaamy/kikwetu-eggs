const CUSTOMER_ORDERS_URL = "/api/customer-orders";

async function readResponse(response) {
  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(data?.error || "Your order could not be placed. Please try again.");
  }

  return data;
}

export async function placeCustomerOrder(order) {
  const response = await fetch(CUSTOMER_ORDERS_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(order),
  });

  return readResponse(response);
}
