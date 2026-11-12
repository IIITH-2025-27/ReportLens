import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { ErrorNote } from "../components/bits";

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

export default function Courses() {
  const ta = useAuth().user.role === "ta";
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    let live = true; // a response that arrives after this page has moved on is dropped
    api.courses()
      .then((d) => live && setRows(d))
      .catch((e) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, []);

  async function create(e) {
    e.preventDefault();
    setBusy(true);
    setFormError("");
    try {
      const c = await api.createCourse({ name, code });
      navigate(`/courses/${c.id}`);
    } catch (err) {
      setFormError(err.message);
      setBusy(false);
    }
  }

  return (
    <>
      <h1>{ta ? "My courses" : "Courses"}</h1>
      {ta && (
        <form className="card upload" onSubmit={create}>
          <h2>Create a course</h2>
          <div className="row">
            <label className="grow">
              Course name
              <input id="course-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Deep Learning" maxLength={200} required />
            </label>
            <label>
              Code (optional)
              <input id="course-code" value={code} onChange={(e) => setCode(e.target.value)} placeholder="CS501" maxLength={40} />
            </label>
            <button className="btn primary" disabled={busy}>
              {busy ? "Creating…" : "Create course"}
            </button>
          </div>
          <ErrorNote error={formError} />
        </form>
      )}

      <ErrorNote error={error} />
      {rows === null && !error && <p className="muted">Loading…</p>}
      {rows?.length === 0 && (
        <p className="empty">
          {ta
            ? "You have no courses yet. Create one above, then add students and release an assignment."
            : "You are not on any course yet. A course appears here when your TA adds your email address to it."}
        </p>
      )}
      {rows?.length > 0 && (
        <div className="cards">
          {rows.map((c) => (
            <Link key={c.id} to={`/courses/${c.id}`} className="course">
              {c.code && <span className="course-code">{c.code}</span>}
              <span className="course-name">{c.name}</span>
              {!ta && <span className="muted small">TA: {c.ta_name}</span>}
              <span className="course-foot">
                <span>{plural(c.assignments, "assignment")}</span>
                {ta && <span>· {plural(c.students, "student")}</span>}
                {ta && c.to_review > 0 && <span className="badge info">{c.to_review} to review</span>}
                {!ta && c.to_do > 0 && <span className="badge warn">{c.to_do} to do</span>}
              </span>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
