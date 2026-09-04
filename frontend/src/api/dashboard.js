const DASHBOARD_URL = "/api/dashboard";

export async function getDashboard() {
  const response = await apiFetch(DASHBOARD_URL);
  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(data?.error || "The dashboard could not be loaded.");
  }

  return data;
}
import { apiFetch } from "./config.js";
