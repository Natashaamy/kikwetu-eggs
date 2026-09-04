const REPORTS_URL = "/api/admin/reports";

function queryString(fromDate, toDate) {
  const parameters = new URLSearchParams();
  if (fromDate) parameters.set("from", fromDate);
  if (toDate) parameters.set("to", toDate);
  const query = parameters.toString();
  return query ? `?${query}` : "";
}

export async function getReport(fromDate, toDate) {
  const response = await fetch(`${REPORTS_URL}${queryString(fromDate, toDate)}`);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(data?.error || "The report could not be loaded.");
  }
  return data;
}

export function getReportExportUrl(fromDate, toDate) {
  return `${REPORTS_URL}/export.csv${queryString(fromDate, toDate)}`;
}
