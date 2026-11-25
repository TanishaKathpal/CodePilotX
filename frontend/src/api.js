
// Backend API base URL
const API_BASE_URL = (import.meta.env.VITE_API_URL || "").replace(/\/+$/, "");

// Tiny wrapper around the backend API.
async function request(path, options) {
  let res;

  try {
    res = await fetch(`${API_BASE_URL}${path}`, options);
  } catch {
    throw new Error("Cannot reach the backend. Please check the backend URL.");
  }

  let body = null;

  try {
    body = await res.json();
  } catch {
    /* non-JSON error page */
  }

  if (!res.ok) {
    throw new Error((body && body.detail) || `Request failed (HTTP ${res.status})`);
  }

  return body;
}

export const getHealth = () => request("/api/health");
export const getSamples = () => request("/api/samples");

export const createJob = (repo_url, issue) =>
  request("/api/jobs", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ repo_url, issue }),
  });

export const getJob = (id) => request(`/api/jobs/${id}`);
