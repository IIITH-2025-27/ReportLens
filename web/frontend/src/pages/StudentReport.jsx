import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, openPdf } from "../api";
import { Crumbs, Due, ErrorNote, StatusBadge, when } from "../components/bits";
import ReviewCard from "../components/ReviewCard";

const NEXT = {
  submitted: "Your report is in the TA queue. You can replace the file until a TA starts checking it.",
  verifying: "A TA is checking your report.",
  verified: "A TA is reviewing the results. You will see the review here.",
  rework_requested: "The TA asked for changes. Read the review below, fix the report and upload the new version.",
  accepted: "Your report was accepted. Nothing more to do.",
};

export default function StudentReport() {
  const { id } = useParams();
  const [s, setS] = useState(null);
  const [error, setError] = useState("");
  const [file, setFile] = useState(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState("");

  useEffect(() => {
    let live = true; // a response that arrives after this page has moved on is dropped
    api.submission(id)
      .then((d) => live && setS(d))
      .catch((e) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [id]);

  async function reupload(e) {
    e.preventDefault();
    if (!file) return setFormError("Choose a PDF file");
    setBusy(true);
    setFormError("");
    try {
      setS(await api.uploadVersion(id, file, note));
      setFile(null);
      setNote("");
      e.target.reset();
    } catch (err) {
      setFormError(err.message);
    }
    setBusy(false);
  }

  if (error) return <ErrorNote error={error} />;
  if (!s) return <p className="muted">Loading…</p>;
  const canUpload = s.status === "rework_requested" || s.status === "submitted";

  return (
    <>
      <Crumbs course={s.course} />
      <div className="title-row">
        <h1>{s.title}</h1>
        <StatusBadge status={s.status} student />
      </div>
      <p className="muted">
        <Due at={s.assignment.due_at} />
        {s.late && " · submitted late"}
      </p>
      {s.assignment.description && <p className="findings">{s.assignment.description}</p>}
      <p className="next">{NEXT[s.status]}</p>

      {canUpload && (
        <form className="card upload" onSubmit={reupload}>
          <h2>{s.status === "rework_requested" ? "Upload the reworked report" : "Replace the file"}</h2>
          <div className="row">
            <label className="grow">
              Report (PDF)
              <input id="re-file" type="file" accept="application/pdf,.pdf" onChange={(e) => setFile(e.target.files[0] || null)} required />
            </label>
            <label className="grow">
              What changed (optional)
              <input id="re-note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Fixed the accuracy in section 2" maxLength={2000} />
            </label>
            <button className="btn primary" disabled={busy}>
              {busy ? "Uploading…" : "Upload new version"}
            </button>
          </div>
          <ErrorNote error={formError} />
        </form>
      )}

      <h2>History</h2>
      <ol className="versions">
        {[...s.versions].reverse().map((v) => (
          <li key={v.id} className="card">
            <div className="version-head">
              <strong>Upload {v.version}</strong>
              <span className="muted small">
                {v.filename} · {when(v.uploaded_at)}
              </span>
              <span className="spacer" />
              <button className="btn" onClick={() => openPdf(v.id).catch((e) => setError(e.message))}>
                Open PDF
              </button>
            </div>
            {v.note && <p className="muted">Your note: {v.note}</p>}
            {v.reviews.length === 0 && <p className="muted">No review yet.</p>}
            {v.reviews.map((r) => (
              <ReviewCard key={r.id} review={r} />
            ))}
          </li>
        ))}
      </ol>
    </>
  );
}
