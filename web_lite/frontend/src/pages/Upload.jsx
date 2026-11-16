import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { ErrorNote, MiniVerdicts, RunBadge, isActive, size, when } from "../components/bits";

const BATCH_MAX = 20; // PDFs per batch; each upload is still one request, sent one after another
const MAX_MB = 25;

// Pick one or more PDFs and upload them. One PDF opens its report page; several are uploaded one after another,
// each with its own status, and the verifier can be started on each as it lands.
export default function Upload() {
  const [items, setItems] = useState([]); // {key, file, state, error, reportId, runStatus, verdicts}
  const [verifyAfter, setVerifyAfter] = useState(true);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [recent, setRecent] = useState(null);
  const input = useRef(null);
  const navigate = useNavigate();

  const loadRecent = () =>
    api.reports()
      .then((r) => {
        setRecent(r.slice(0, 5));
        return r;
      })
      .catch(() => setRecent([]));

  useEffect(() => {
    loadRecent();
  }, []);

  // After a batch, follow each report's latest run until none is queued or running.
  const following = items.some((i) => i.reportId && isActive(i.runStatus));
  useEffect(() => {
    if (!following) return;
    let live = true;
    const t = setTimeout(async () => {
      const all = await loadRecent();
      if (!live || !all) return;
      const byId = Object.fromEntries(all.map((r) => [r.id, r]));
      setItems((old) =>
        old.map((i) => {
          const r = i.reportId && byId[i.reportId];
          return r?.latest_run ? { ...i, runStatus: r.latest_run.status, verdicts: r.latest_run.verdicts } : i;
        })
      );
    }, 3000);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [items, following]);

  function add(fileList) {
    setError("");
    const incoming = [...(fileList || [])];
    if (input.current) input.current.value = ""; // so picking the same file again still fires onChange
    if (!incoming.length) return;
    const notes = [];
    const next = items.filter((i) => i.state === "ready"); // adding after a finished batch starts a new one
    const seen = new Set(next.map((i) => `${i.file.name}:${i.file.size}`));
    for (const f of incoming) {
      if (f.type !== "application/pdf" && !f.name.toLowerCase().endsWith(".pdf")) {
        notes.push(`${f.name}: not a PDF`);
        continue;
      }
      if (f.size > MAX_MB * 1024 * 1024) {
        notes.push(`${f.name}: larger than ${MAX_MB} MB`);
        continue;
      }
      const k = `${f.name}:${f.size}`;
      if (seen.has(k)) continue; // the same file twice
      if (next.length >= BATCH_MAX) {
        notes.push(`Only ${BATCH_MAX} PDFs per batch; the rest were left out`);
        break;
      }
      seen.add(k);
      next.push({ key: `${k}:${Date.now()}:${next.length}`, file: f, state: "ready" });
    }
    setItems(next);
    if (notes.length) setError(notes.join(". "));
  }

  const update = (key, patch) => setItems((old) => old.map((i) => (i.key === key ? { ...i, ...patch } : i)));

  async function start(e) {
    e.preventDefault();
    const todo = items.filter((i) => i.state === "ready");
    if (!todo.length) return setError("Choose one or more PDF files");
    setBusy(true);
    setError("");

    if (todo.length === 1 && items.length === 1) {
      // one PDF: as before, open its report page (with the verifier already started if asked)
      try {
        const r = await api.upload(todo[0].file);
        if (verifyAfter) await api.verify(r.id).catch(() => {});
        navigate(`/reports/${r.id}`);
      } catch (err) {
        setError(err.message);
        setBusy(false);
      }
      return;
    }

    for (const it of todo) {
      update(it.key, { state: "uploading", error: "" });
      let report;
      try {
        report = await api.upload(it.file);
      } catch (err) {
        update(it.key, { state: "failed", error: err.message });
        continue;
      }
      update(it.key, { state: "uploaded", reportId: report.id });
      if (!verifyAfter) continue;
      try {
        const run = await api.verify(report.id);
        update(it.key, { runStatus: run.status, queue: run.queue_position });
      } catch (err) {
        update(it.key, { verifyError: err.status === 429 ? "The verifier queue is full; start it from the report page later." : err.message });
      }
    }
    setBusy(false);
    loadRecent();
  }

  const ready = items.filter((i) => i.state === "ready");
  const batch = items.length > 1 || items.some((i) => i.state !== "ready");
  const doneCount = items.filter((i) => i.state === "uploaded").length;
  const failedCount = items.filter((i) => i.state === "failed").length;

  return (
    <>
      <h1>Check a report's chart claims</h1>
      <p className="muted" style={{ maxWidth: "75ch" }}>
        Upload one report or a batch of reports as PDFs. The verifier reads every sentence that quotes a number from a chart, reads the chart itself, and lists the claims that do not match. No account needed; uploads are listed in the history for everyone.
      </p>

      <form className="card upload" onSubmit={start}>
        <h2>1. Upload reports</h2>
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
            if (!busy) add(e.dataTransfer.files);
          }}
        >
          <input ref={input} id="file" type="file" multiple accept="application/pdf,.pdf" disabled={busy} onChange={(e) => add(e.target.files)} />
          {ready.length && !batch ? (
            <>
              <strong>{ready[0].file.name}</strong>
              <span className="muted small">{size(ready[0].file.size)} · drop or click to add more PDFs for a batch</span>
            </>
          ) : (
            <>
              <strong>{items.length ? "Drop more PDFs here or click to add" : "Drop PDFs here or click to choose"}</strong>
              <span className="muted small">
                One or several at once · up to {BATCH_MAX} per batch · {MAX_MB} MB each
              </span>
            </>
          )}
        </label>

        {batch && (
          <ul className="batch" aria-live="polite">
            {items.map((i) => (
              <li key={i.key} className={`batch-row batch-${i.state}`}>
                <div className="batch-name">
                  {i.reportId ? <Link to={`/reports/${i.reportId}`}>{i.file.name}</Link> : <span>{i.file.name}</span>}
                  <span className="muted small"> · {size(i.file.size)}</span>
                  {i.error && <div className="small batch-error">{i.error}</div>}
                  {i.verifyError && <div className="small batch-error">{i.verifyError}</div>}
                </div>
                <div className="batch-state">
                  {i.state === "ready" && (
                    <>
                      <span className="muted small">Ready</span>
                      {!busy && (
                        <button type="button" className="btn ghost" aria-label={`Remove ${i.file.name}`} onClick={() => setItems((old) => old.filter((x) => x.key !== i.key))}>
                          Remove
                        </button>
                      )}
                    </>
                  )}
                  {i.state === "uploading" && (
                    <span className="running small">
                      <span className="spinner" aria-hidden="true" /> Uploading…
                    </span>
                  )}
                  {i.state === "failed" && <span className="badge bad">Upload failed</span>}
                  {i.state === "uploaded" &&
                    (i.runStatus ? i.runStatus === "done" ? <MiniVerdicts verdicts={i.verdicts} /> : <RunBadge status={i.runStatus} /> : <span className="badge ok">Uploaded</span>)}
                </div>
              </li>
            ))}
          </ul>
        )}

        <div className="row end batch-actions">
          <label className="batch-verify small">
            <input type="checkbox" checked={verifyAfter} disabled={busy} onChange={(e) => setVerifyAfter(e.target.checked)} /> Start the verifier on each report after upload
          </label>
          <span className="spacer" />
          {batch && !busy && items.some((i) => i.state !== "ready") && (
            <button type="button" className="btn" onClick={() => setItems([])}>
              Clear list
            </button>
          )}
          <button className="btn primary" disabled={busy || !ready.length}>
            {busy ? `Uploading ${Math.min(doneCount + failedCount + 1, items.length)} of ${items.length}…` : ready.length > 1 ? `Upload ${ready.length} PDFs` : "Upload"}
          </button>
        </div>
        {batch && !busy && doneCount + failedCount > 0 && (
          <p className="muted small">
            {doneCount} uploaded{failedCount ? `, ${failedCount} failed` : ""}.{" "}
            {verifyAfter ? "The verifier checks one report at a time; each row updates as its run finishes." : "Open a report to start the verifier."}
          </p>
        )}
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
