import { useEffect, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { Crumbs, Due, ErrorNote } from "../components/bits";

// An assignment the student has not submitted to yet. Once there is a report, the report page takes over.
export default function StudentAssignment() {
  const { id } = useParams();
  const [a, setA] = useState(null);
  const [error, setError] = useState("");
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    let live = true; // a response that arrives after this page has moved on is dropped
    api.assignment(id)
      .then((d) => live && setA(d))
      .catch((e) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [id]);

  async function upload(e) {
    e.preventDefault();
    if (!file) return setFormError("Choose a PDF file");
    setBusy(true);
    setFormError("");
    try {
      const s = await api.submit(id, file);
      navigate(`/reports/${s.id}`, { replace: true });
    } catch (err) {
      setFormError(err.message);
      setBusy(false);
    }
  }

  if (error) return <ErrorNote error={error} />;
  if (!a) return <p className="muted">Loading…</p>;
  if (a.submission) return <Navigate to={`/reports/${a.submission.id}`} replace />;

  return (
    <>
      <Crumbs course={a.course} />
      <h1>{a.title}</h1>
      <p className="muted">
        <Due at={a.due_at} />
      </p>
      {a.description && <p className="findings">{a.description}</p>}
      <form className="card upload" onSubmit={upload}>
        <h2>Upload your report</h2>
        <p className="muted">Upload the PDF. It goes to your TA, who checks the numbers against your charts and sends back a review.</p>
        <div className="row">
          <label className="grow">
            Report (PDF)
            <input id="new-file" type="file" accept="application/pdf,.pdf" onChange={(e) => setFile(e.target.files[0] || null)} required />
          </label>
          <button className="btn primary" disabled={busy}>
            {busy ? "Uploading…" : "Submit report"}
          </button>
        </div>
        <ErrorNote error={formError} />
      </form>
    </>
  );
}
