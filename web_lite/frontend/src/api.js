// One place for every call to the lite backend. No sign-in, so files can be linked to directly.
const BASE = import.meta.env.VITE_API_URL || "";

function message(detail, status) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg?.replace(/^Value error, /, "")).filter(Boolean).join(". ");
  return `Request failed (${status})`;
}

async function request(path, { method = "GET", form } = {}) {
  let res;
  try {
    res = await fetch(BASE + path, { method, body: form });
  } catch {
    throw new Error("Cannot reach the server. Check that the backend is running.");
  }
  if (!res.ok) {
    let detail;
    try {
      detail = (await res.json()).detail;
    } catch {
      /* not JSON */
    }
    const err = new Error(message(detail, res.status));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

export const api = {
  reports: (q = "") => request(`/api/reports${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  report: (id) => request(`/api/reports/${id}`),
  upload: (file) => {
    const f = new FormData();
    f.append("file", file);
    return request("/api/reports", { method: "POST", form: f });
  },
  remove: (id) => request(`/api/reports/${id}`, { method: "DELETE" }),
  verify: (id) => request(`/api/reports/${id}/verify`, { method: "POST" }),
  run: (id) => request(`/api/runs/${id}`),
};

export const pdfUrl = (reportId) => `${BASE}/api/reports/${reportId}/pdf`;
export const figureUrl = (runId, figureId) => `${BASE}/api/runs/${runId}/figures/${encodeURIComponent(figureId)}`;
