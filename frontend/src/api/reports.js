const REPORTS_URL = "/api/admin/reports";

function queryString(fromDate, toDate) {
  const parameters = new URLSearchParams();
  if (fromDate) parameters.set("from", fromDate);
  if (toDate) parameters.set("to", toDate);
  const query = parameters.toString();
  return query ? `?${query}` : "";
}

export async function getReport(fromDate, toDate) {
  const response = await apiFetch(`${REPORTS_URL}${queryString(fromDate, toDate)}`);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(data?.error || "The report could not be loaded.");
  }
  return data;
}

export async function downloadReportCsv(fromDate, toDate) {
  const response = await apiFetch(`${REPORTS_URL}/export.csv${queryString(fromDate, toDate)}`);
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.error || "The report export could not be downloaded.");
  }
  return response.blob();
}
import { apiFetch } from "./config.js";
