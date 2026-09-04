const PRODUCTS_URL = "/api/products";

async function readResponse(response) {
  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(data?.error || "The product request failed. Please try again.");
  }

  return data;
}

export async function getProducts() {
  const response = await fetch(PRODUCTS_URL);
  return readResponse(response);
}

export async function createProduct(product) {
  const response = await fetch(PRODUCTS_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(product),
  });

  return readResponse(response);
}

export async function updateProduct(productId, product) {
  const response = await fetch(`${PRODUCTS_URL}/${productId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(product),
  });

  return readResponse(response);
}

export async function deleteProduct(productId) {
  const response = await fetch(`${PRODUCTS_URL}/${productId}`, {
    method: "DELETE",
  });

  return readResponse(response);
}

export async function addProductStock(productId, quantity) {
  const response = await fetch(`${PRODUCTS_URL}/${productId}/stock`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ quantity }),
  });
  return readResponse(response);
}

export async function setProductStock(productId, stockQuantity) {
  const response = await fetch(`${PRODUCTS_URL}/${productId}/stock`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ stock_quantity: stockQuantity }),
  });
  return readResponse(response);
}
