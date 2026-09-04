const configuredApiUrl = import.meta.env.VITE_API_URL?.trim();

if (!configuredApiUrl) {
  throw new Error("VITE_API_URL is not configured.");
}

export const API_BASE_URL = configuredApiUrl.replace(/\/+$/, "");

export function apiUrl(path) {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE_URL}${normalizedPath}`;
}

export function apiFetch(path, options = {}) {
  return fetch(apiUrl(path), {
    ...options,
    credentials: "include",
  });
}
