import { apiFetch } from "./config.js";

const AUTH_URL = "/api/auth";

async function request(path, options = {}) {
  const response = await apiFetch(`${AUTH_URL}${path}`, options);
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.error || "Authentication request failed.");
  return data;
}

const jsonOptions = (body) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
export const getCurrentUser = () => request("/me");
export const registerCustomer = (data) => request("/register", jsonOptions(data));
export const loginUser = (data) => request("/login", jsonOptions(data));
export const logoutUser = () => request("/logout", { method: "POST" });
