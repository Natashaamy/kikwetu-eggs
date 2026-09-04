const ADMIN_CUSTOMERS_URL = "/api/admin/customers";

async function readResponse(response) {
  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(data?.error || "The customer request failed. Please try again.");
  }

  return data;
}

export async function getAdminCustomers() {
  return readResponse(await fetch(ADMIN_CUSTOMERS_URL));
}

export async function getAdminCustomer(customerId) {
  return readResponse(await fetch(`${ADMIN_CUSTOMERS_URL}/${customerId}`));
}

export async function deleteAdminCustomer(customerId) {
  return readResponse(await fetch(`${ADMIN_CUSTOMERS_URL}/${customerId}`, {
    method: "DELETE",
  }));
}
