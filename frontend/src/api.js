// Tiny wrapper around the backend API. All errors become readable Error messages.
async function request(path, options) {
  let res;
  try {
    res = await fetch(path, options);
  } catch {
    throw new Error("Cannot reach the backend. Is it running on port 8000?");
  }
  let body = null;
  try {
    body = await res.json();
  } catch {
    /* non-JSON error page */
  }
  if (!res.ok) throw new Error((body && body.detail) || `Request failed (HTTP ${res.status})`);
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
