import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { ErrorNote, MiniVerdicts, RunBadge, size, when } from "../components/bits";

// Step 1: pick a PDF and upload it. The report page then offers the Verify button and shows the results.
export default function Upload() {
  const [file, setFile] = useState(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [recent, setRecent] = useState(null);
  const input = useRef(null);
  const navigate = useNavigate();

  useEffect(() => {
    let live = true;
    api.reports()
      .then((r) => live && setRecent(r.slice(0, 5)))
      .catch(() => live && setRecent([]));
    return () => {
      live = false;
    };
  }, []);

  function pick(f) {
    setError("");
    if (!f) return;
    if (f.type !== "application/pdf" && !f.name.toLowerCase().endsWith(".pdf")) return setError("Choose a PDF file");
    setFile(f);
  }

  async function upload(e) {
    e.preventDefault();
    if (!file) return setError("Choose a PDF file");
    setBusy(true);
    setError("");
    try {
      const r = await api.upload(file);
      navigate(`/reports/${r.id}`);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Check a report's chart claims</h1>
      <p className="muted" style={{ maxWidth: "75ch" }}>
        Upload a report as a PDF. The verifier reads every sentence that quotes a number from a chart, reads the chart itself, and lists the claims that do not match. No account needed; uploads are listed in the history for everyone.
      </p>

      <form className="card upload" onSubmit={upload}>
        <h2>1. Upload the report</h2>
        <label
          className={`drop ${over ? "over" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setOver(false);
            pick(e.dataTransfer.files[0]);
          }}
        >
          <input ref={input} id="file" type="file" accept="application/pdf,.pdf" onChange={(e) => pick(e.target.files[0] || null)} />
          {file ? (
            <>
              <strong>{file.name}</strong>
              <span className="muted small">{size(file.size)} · click to choose another file</span>
            </>
          ) : (
            <>
              <strong>Drop a PDF here or click to choose</strong>
              <span className="muted small">Up to 25 MB</span>
            </>
          )}
        </label>
        <div className="row end">
          <button className="btn primary" disabled={busy || !file}>
            {busy ? "Uploading…" : "Upload"}
          </button>
        </div>
        <ErrorNote error={error} />
      </form>

      <section className="card">
        <div className="section-head">
          <h2>Recent uploads</h2>
          <span className="spacer" />
          <Link to="/history">See all</Link>
        </div>
        {recent === null && <p className="muted">Loading…</p>}
        {recent?.length === 0 && <p className="muted">Nothing uploaded yet.</p>}
        {recent?.length > 0 && (
          <ul className="people">
            {recent.map((r) => (
              <li key={r.id}>
                <div>
                  <Link to={`/reports/${r.id}`}>{r.filename}</Link>
                  <div className="muted small">{when(r.uploaded_at)}</div>
                </div>
                {r.latest_run ? r.latest_run.status === "done" ? <MiniVerdicts verdicts={r.latest_run.verdicts} /> : <RunBadge status={r.latest_run.status} /> : <span className="muted small">Not verified</span>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
