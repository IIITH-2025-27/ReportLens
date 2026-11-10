import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, pdfUrl } from "../api";
import ClaimCard from "../components/ClaimCard";
import { ErrorNote, RunBadge, VERDICT_ORDER, VerdictBadge, isActive, size, verdictLabel, when } from "../components/bits";

// One report: view the PDF, run the verifier, read the results. ?run=<id> picks an earlier run; default the latest.
export default function Report() {
  const { id } = useParams();
  const [params, setParams] = useSearchParams();
  const [report, setReport] = useState(null);
  const [run, setRun] = useState(null); // the selected run, with claims once done
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState(false);
  const [showPdf, setShowPdf] = useState(false);
  const [filter, setFilter] = useState("ALL");

  const navigate = useNavigate();
  const wanted = params.get("run");

  // isLive tells a slow response whether the page still wants it; a late, stale one is dropped.
  const load = useCallback(
    async (isLive = () => true) => {
      const rp = await api.report(id);
      const pick = rp.runs.find((r) => String(r.id) === wanted) || rp.runs[rp.runs.length - 1];
      const r = pick ? await api.run(pick.id) : null;
      if (!isLive()) return;
      setReport(rp);
      setRun(r);
    },
    [id, wanted]
  );

  useEffect(() => {
    let live = true;
    load(() => live).catch((e) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [load]);

  // While the verifier is working, ask again every 3 seconds.
  useEffect(() => {
    if (!run || !isActive(run.status)) return;
    let live = true;
    const t = setTimeout(() => load(() => live).catch((e) => live && setActionError(e.message)), 3000);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [run, load]);

  useEffect(() => setFilter("ALL"), [run?.id]);

  async function verify() {
    setBusy(true);
    setActionError("");
    try {
      const r = await api.verify(id);
      setParams({ run: String(r.id) }, { replace: false });
    } catch (e) {
      setActionError(e.message);
    }
    setBusy(false);
  }

  async function remove() {
    if (!window.confirm(`Delete "${report.filename}" and all its verifier runs? This cannot be undone.`)) return;
    setBusy(true);
    setActionError("");
    try {
      await api.remove(id);
      navigate("/history", { replace: true });
    } catch (e) {
      setActionError(e.message);
      setBusy(false);
    }
  }

  const claims = run?.claims || [];
  const counts = useMemo(() => claims.reduce((a, c) => ({ ...a, [c.verdict]: (a[c.verdict] || 0) + 1 }), {}), [claims]);
  const shown = useMemo(() => {
    const list = filter === "ALL" ? claims.filter((c) => c.verdict !== "SKIPPED") : claims.filter((c) => c.verdict === filter);
    return [...list].sort((a, b) => VERDICT_ORDER.indexOf(a.verdict) - VERDICT_ORDER.indexOf(b.verdict) || a.position - b.position);
  }, [claims, filter]);

  if (error) return <ErrorNote error={error} />;
  if (!report) return <p className="muted">Loading…</p>;

  const anyActive = report.runs.some((r) => isActive(r.status));
  const latestId = report.runs[report.runs.length - 1]?.id;
  const sum = run?.summary;

  return (
    <>
      <p className="crumb">
        <Link to="/history">History</Link> / report {report.id}
      </p>
      <h1 style={{ overflowWrap: "anywhere" }}>{report.filename}</h1>
      <p className="muted">
        Uploaded {when(report.uploaded_at)} · {size(report.size_bytes)} · {report.runs.length} verifier run{report.runs.length === 1 ? "" : "s"}
      </p>

      <section className="card">
        <div className="section-head">
          <h2>Report</h2>
          <span className="spacer" />
          <button className="btn" onClick={() => setShowPdf(!showPdf)} aria-expanded={showPdf}>
            {showPdf ? "Hide PDF" : "View PDF"}
          </button>
          <a className="btn" href={pdfUrl(report.id)} target="_blank" rel="noopener noreferrer" style={{ textDecoration: "none" }}>
            Open in new tab
          </a>
          <button className="btn primary" onClick={verify} disabled={busy || anyActive}>
            {anyActive ? "Verifier running…" : report.runs.length ? "Run verifier again" : "Verify"}
          </button>
          <button className="btn danger" onClick={remove} disabled={busy || anyActive} title={anyActive ? "Wait for the verifier to finish" : undefined}>
            Delete
          </button>
        </div>
        {showPdf && <iframe className="pdf-frame" src={pdfUrl(report.id)} title={`PDF: ${report.filename}`} />}
        {!report.runs.length && <p className="muted">The verifier has not been run on this report yet. Press Verify: it reads every number in the report against the charts and lists what does not match.</p>}
        <ErrorNote error={actionError} />
      </section>

      {report.runs.length > 1 && (
        <section className="card">
          <h2>Runs</h2>
          <p className="muted small">Every run is kept. Pick one to see its results.</p>
          <div className="runs-pick" role="group" aria-label="Verifier runs">
            {[...report.runs].reverse().map((r, i) => (
              <button key={r.id} className={`chip ${run?.id === r.id ? "on" : ""}`} aria-pressed={run?.id === r.id} onClick={() => setParams(r.id === latestId ? {} : { run: String(r.id) })}>
                Run {report.runs.length - i} · {when(r.created_at)} <RunBadge status={r.status} />
              </button>
            ))}
          </div>
        </section>
      )}

      {run && (
        <section className="card">
          <div className="section-head">
            <h2>Results{report.runs.length > 1 && ` · run ${report.runs.findIndex((r) => r.id === run.id) + 1}`}</h2>
            <RunBadge status={run.status} />
            {run.id !== latestId && <span className="muted small">an earlier run</span>}
          </div>

          {isActive(run.status) && (
            <p className="running">
              <span className="spinner" aria-hidden="true" />{" "}
              {run.status === "queued"
                ? `Waiting for the worker${run.queue_position > 1 ? ` (${run.queue_position - 1} report${run.queue_position === 2 ? "" : "s"} ahead)` : ""}…`
                : "Reading charts. This can take a minute or more per report; the first run also loads the models."}
            </p>
          )}

          {run.status === "failed" && (
            <div className="error" role="alert">
              <strong>The verifier could not finish.</strong>
              <div className="small">{run.error}</div>
            </div>
          )}

          {run.status === "done" && sum && (
            <>
              <div className="tiles">
                {VERDICT_ORDER.filter((v) => v !== "SKIPPED").map((v) => (
                  <div key={v} className="tile">
                    <span className="tile-n">{counts[v] || 0}</span>
                    <VerdictBadge verdict={v} />
                  </div>
                ))}
              </div>
              <p className="muted small">
                {sum.figures} figures · {sum.sentences} sentences · {sum.tool_calls} tool calls · {sum.seconds}s · policy <code>{sum.policy}</code> · parser <code>{sum.parser}</code> · tools <code>{sum.tools.join(", ")}</code> · finished {when(run.finished_at)}
              </p>

              <h3 style={{ marginTop: 16 }}>Analysis</h3>
              <p className="muted">Open a finding to see the chart, each tool's reading and the reasoning. "Not sure" means the verifier could not decide; treat a flag as "needs a look".</p>
              <div className="filters" role="group" aria-label="Filter findings">
                <button className={`chip ${filter === "ALL" ? "on" : ""}`} aria-pressed={filter === "ALL"} onClick={() => setFilter("ALL")}>
                  All chart claims <span className="count">{claims.filter((c) => c.verdict !== "SKIPPED").length}</span>
                </button>
                {VERDICT_ORDER.filter((v) => counts[v]).map((v) => (
                  <button key={v} className={`chip ${filter === v ? "on" : ""}`} aria-pressed={filter === v} onClick={() => setFilter(v)}>
                    {verdictLabel(v)} <span className="count">{counts[v]}</span>
                  </button>
                ))}
              </div>
              {shown.length === 0 && <p className="empty">{claims.length === 0 ? "The verifier found no sentences with numbers in this report." : "Nothing with this verdict."}</p>}
              <ul className="claims">
                {shown.map((c) => (
                  <ClaimCard key={c.id} claim={c} runId={run.id} figures={run.figures} />
                ))}
              </ul>
            </>
          )}
        </section>
      )}
    </>
  );
}
