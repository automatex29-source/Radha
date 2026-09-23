import axios from "axios";

// REACT_APP_BACKEND_URL is inlined by Vite only when it is set in frontend/.env.
// Without it, `process` does not exist in the browser, so guard the lookup and
// fall back to same-origin requests (served via the Vite /api proxy in dev).
const BACKEND_URL = (
  (typeof process !== "undefined" && process.env && process.env.REACT_APP_BACKEND_URL) ||
  import.meta.env.VITE_BACKEND_URL ||
  ""
).replace(/\/+$/, "");
export const API = `${BACKEND_URL}/api`;

/** Absolute URL for an /api path (for links people copy or open in a new tab). */
export const absoluteUrl = (path) => `${BACKEND_URL || window.location.origin}${path}`;

const TOKEN_KEY = "radha_token";

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t) => localStorage.setItem(TOKEN_KEY, t);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

export const api = axios.create({ baseURL: API });

// <img>/<audio>/download links can't send headers, so media URLs carry the token.
export const mediaUrl = (path) =>
  `${BACKEND_URL}${path}${path.includes("?") ? "&" : "?"}auth=${encodeURIComponent(getToken() || "")}`;

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export function formatApiError(err) {
  const detail = err?.response?.data?.detail;
  if (detail == null) return err?.message || "Something went wrong.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((e) => (e?.msg ? e.msg : JSON.stringify(e))).join(" ");
  if (detail?.msg) return detail.msg;
  return String(detail);
}
