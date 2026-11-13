import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { ErrorNote, MiniVerdicts, RunBadge, isActive, size, when } from "../components/bits";

// Every uploaded report, newest first. Opening one shows its earlier analyses and lets you run the verifier again.
export default function History() {
  const [rows, setRows] = useState(null);
  const [q, setQ] = useState("");
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState(null);
  const navigate = useNavigate();

  async function remove(e, r) {
    e.stopPropagation();
    if (!window.confirm(`Delete "${r.filename}" and all its verifier runs? This cannot be undone.`)) return;
    setDeleting(r.id);
    setError("");
    try {
      await api.remove(r.id);
      setRows((rs) => rs.filter((x) => x.id !== r.id));
    } catch (err) {
      setError(err.message);
    }
    setDeleting(null);
  }

  useEffect(() => {
    let live = true;
    const t = setTimeout(() => {
      api.reports(q.trim())
        .then((r) => live && (setRows(r), setError("")))
        .catch((e) => live && setError(e.message));
    }, q ? 250 : 0);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [q]);

  return (
    <>
      <div className="title-row">
        <h1>History</h1>
        <span className="spacer" />
        <Link className="btn primary" to="/" style={{ textDecoration: "none" }}>
          Upload a report
        </Link>
      </div>
      <p className="muted">All uploaded reports, newest first. Open one to see its results or run the verifier on it again.</p>
      <label className="search">
        Search by file name
        <input id="q" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="report.pdf" />
      </label>
      <ErrorNote error={error} />
      {rows === null && !error && <p className="muted">Loading…</p>}
      {rows?.length === 0 && <p className="empty">{q ? "No report matches." : "Nothing uploaded yet."}</p>}
      {rows?.length > 0 && (
        <div className="table-wrap" style={{ marginTop: 16 }}>
          <table>
            <thead>
              <tr>
                <th>Report</th>
                <th>Uploaded</th>
                <th>Runs</th>
                <th>Latest result</th>
                <th>
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="history-row" onClick={() => navigate(`/reports/${r.id}`)}>
                  <td>
                    <Link to={`/reports/${r.id}`} onClick={(e) => e.stopPropagation()}>
                      {r.filename}
                    </Link>
                    <div className="muted small">{size(r.size_bytes)}</div>
                  </td>
                  <td className="small">{when(r.uploaded_at)}</td>
                  <td className="num">{r.runs}</td>
                  <td>
                    {!r.latest_run && <span className="muted small">Not verified</span>}
                    {r.latest_run && r.latest_run.status !== "done" && <RunBadge status={r.latest_run.status} />}
                    {r.latest_run?.status === "done" && <MiniVerdicts verdicts={r.latest_run.verdicts} />}
                  </td>
                  <td className="actions">
                    <button
                      className="btn ghost danger"
                      disabled={deleting === r.id || isActive(r.latest_run?.status)}
                      title={isActive(r.latest_run?.status) ? "Wait for the verifier to finish" : undefined}
                      onClick={(e) => remove(e, r)}
                    >
                      {deleting === r.id ? "Deleting…" : "Delete"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
