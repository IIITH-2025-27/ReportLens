// One place for every call to the backend.
const BASE = import.meta.env.VITE_API_URL || "";
const TOKEN_KEY = "reportlens_token";

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t) => (t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY));

function message(detail, status) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg?.replace(/^Value error, /, "")).filter(Boolean).join(". ");
  return `Request failed (${status})`;
}

async function request(path, { method = "GET", json, form, blob = false } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let body;
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  } else if (form) {
    body = form;
  }
  let res;
  try {
    res = await fetch(BASE + path, { method, headers, body });
  } catch {
    throw new Error("Cannot reach the server. Check that the backend is running.");
  }
  if (res.status === 401 && token) {
    setToken(null);
    window.dispatchEvent(new Event("reportlens:signed-out"));
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
  return blob ? res.blob() : res.json();
}

export const api = {
  signup: (data) => request("/api/auth/signup", { method: "POST", json: data }),
  signin: (data) => request("/api/auth/signin", { method: "POST", json: data }),
  me: () => request("/api/auth/me"),

  courses: () => request("/api/courses"),
  course: (id) => request(`/api/courses/${id}`),
  createCourse: (data) => request("/api/courses", { method: "POST", json: data }),
  addStudents: (courseId, emails) => request(`/api/courses/${courseId}/students`, { method: "POST", json: { emails } }),
  removeStudent: (courseId, memberId) => request(`/api/courses/${courseId}/students/${memberId}`, { method: "DELETE" }),
  createAssignment: (courseId, data) => request(`/api/courses/${courseId}/assignments`, { method: "POST", json: data }),
  assignment: (id) => request(`/api/assignments/${id}`),

  submission: (id) => request(`/api/submissions/${id}`),
  submit: (assignmentId, file) => {
    const f = new FormData();
    f.append("file", file);
    return request(`/api/assignments/${assignmentId}/submissions`, { method: "POST", form: f });
  },
  uploadVersion: (id, file, note) => {
    const f = new FormData();
    f.append("file", file);
    f.append("note", note || "");
    return request(`/api/submissions/${id}/versions`, { method: "POST", form: f });
  },
  pdf: (versionId) => request(`/api/versions/${versionId}/pdf`, { blob: true }),

  verify: (versionId) => request(`/api/versions/${versionId}/verify`, { method: "POST" }),
  run: (id) => request(`/api/runs/${id}`),
  figure: (runId, figureId) => request(`/api/runs/${runId}/figures/${encodeURIComponent(figureId)}`, { blob: true }),
  decideClaim: (id, data) => request(`/api/claims/${id}`, { method: "PATCH", json: data }),
  sendReview: (versionId, data) => request(`/api/versions/${versionId}/review`, { method: "POST", json: data }),
};

// Files need the auth header, so they are fetched and opened from memory.
export async function openPdf(versionId) {
  const url = URL.createObjectURL(await api.pdf(versionId));
  window.open(url, "_blank", "noopener");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
