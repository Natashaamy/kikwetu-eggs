import { apiFetch } from "./config.js";

const AUTH_URL = "/api/auth";

async function request(path, options = {}) {
  // Allow a sleeping backend time to wake, but always release the login form.
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 60000);
  try {
    const response = await apiFetch(`${AUTH_URL}${path}`, { ...options, signal: controller.signal });
    const data = await response.json().catch((error) => {
      if (controller.signal.aborted) throw error;
      return null;
    });
    if (!response.ok) {
      throw new Error(data?.error || (response.status >= 500
        ? "The server is temporarily unavailable or waking up. Please try again shortly."
        : "Authentication request failed. Please try again."));
    }
    if (!data || typeof data !== "object") {
      throw new Error("The server returned an unexpected response. Please try again shortly.");
    }
    return data;
  } catch (error) {
    if (controller.signal.aborted) {
      throw new Error("The server took too long to respond. It may be waking up. Please try again.");
    }
    if (error instanceof TypeError) {
      throw new Error("Unable to reach the server. Check your connection and try again shortly.");
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

const jsonOptions = (body) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
export const getCurrentUser = () => request("/me");
export const registerCustomer = (data) => request("/register", jsonOptions(data));
export const loginUser = (data) => request("/login", jsonOptions(data));
export const logoutUser = () => request("/logout", { method: "POST" });
