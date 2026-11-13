import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api, openPdf } from "../api";
import ClaimCard from "../components/ClaimCard";
import { Crumbs, ErrorNote, StatusBadge, VERDICT_ORDER, VerdictBadge, num, verdictLabel, when } from "../components/bits";
import ReviewCard from "../components/ReviewCard";

export default function TAReport() {
  const { id } = useParams();
  const [s, setS] = useState(null);
  const [run, setRun] = useState(null); // latest run of the latest upload, with claims once done
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState("ALL");
  const [score, setScore] = useState("");
  const [findings, setFindings] = useState("");
  const timer = useRef(null);

  const latest = s?.versions[s.versions.length - 1];

  // isLive tells a slow response whether the page still wants it; a late, stale one is dropped.
  const load = useCallback(async (isLive = () => true) => {
    const sub = await api.submission(id);
    const v = sub.versions[sub.versions.length - 1];
    const last = v.runs[v.runs.length - 1];
    const r = last ? await api.run(last.id) : null;
    if (!isLive()) return last;
    setS(sub);
    setRun(r);
    return last;
  }, [id]);

  useEffect(() => {
    let live = true;
    load(() => live).catch((e) => live && setError(e.message));
    return () => {
      live = false;
      clearTimeout(timer.current);
    };
  }, [load]);

  // While the verifier is working, ask again every 3 seconds.
  useEffect(() => {
    if (!run || !["queued", "running"].includes(run.status)) return;
    let live = true;
    timer.current = setTimeout(() => load(() => live).catch((e) => live && setError(e.message)), 3000);
    return () => {
      live = false;
      clearTimeout(timer.current);
    };
  }, [run, load]);

  async function verify() {
    setBusy(true);
    setActionError("");
    try {
      await api.verify(latest.id);
      await load();
    } catch (e) {
      setActionError(e.message);
    }
    setBusy(false);
  }

  async function send(decision) {
    setBusy(true);
    setActionError("");
    try {
      await api.sendReview(latest.id, { decision, score: score === "" ? null : Number(score), findings });
      setScore("");
      setFindings("");
      await load();
    } catch (e) {
      setActionError(e.message);
    }
    setBusy(false);
  }

  const claims = run?.claims || [];
  const counts = useMemo(() => claims.reduce((a, c) => ({ ...a, [c.verdict]: (a[c.verdict] || 0) + 1 }), {}), [claims]);
  const shown = useMemo(() => {
    const list = filter === "ALL" ? claims.filter((c) => c.verdict !== "SKIPPED") : claims.filter((c) => c.verdict === filter);
    return [...list].sort((a, b) => VERDICT_ORDER.indexOf(a.verdict) - VERDICT_ORDER.indexOf(b.verdict) || a.position - b.position);
  }, [claims, filter]);
  const confirmed = claims.filter((c) => c.ta_decision === "confirmed");

  function insertConfirmed() {
    const lines = confirmed.map(
      (c) => `- Page ${c.page + 1}: "${c.sentence}"${c.estimate !== null ? ` The chart reads about ${num(c.estimate)}.` : ""}${c.ta_note ? ` ${c.ta_note}` : ""}`
    );
    setFindings((f) => (f ? f.trimEnd() + "\n" : "") + lines.join("\n"));
  }

  if (error) return <ErrorNote error={error} />;
  if (!s) return <p className="muted">Loading…</p>;

  const working = run && ["queued", "running"].includes(run.status);
  const closed = s.status === "accepted" || s.status === "rework_requested";
  const sum = run?.summary;

  return (
    <>
      <Crumbs course={s.course} assignment={s.assignment} />
      <div className="title-row">
        <h1>{s.title}</h1>
        <StatusBadge status={s.status} />
      </div>
      <p className="muted">
        {s.student.name} · {s.student.email} · upload {latest.version} of {s.versions.length} · {latest.filename} · {when(latest.uploaded_at)}
        {s.late && " · submitted late"}
      </p>
      {latest.note && <p className="next">Student's note on this upload: {latest.note}</p>}

      <section className="card">
        <div className="section-head">
          <h2>1. Verify</h2>
          <span className="spacer" />
          <button className="btn" onClick={() => openPdf(latest.id).catch((e) => setActionError(e.message))}>
            Open PDF
          </button>
          {!closed && (
            <button className="btn primary" onClick={verify} disabled={busy || working}>
              {working ? "Verifier running…" : run ? "Run verifier again" : "Run verifier"}
            </button>
          )}
        </div>
        {!run && <p className="muted">The verifier has not been run on this upload. It reads every number in the report against the charts and lists what does not match.</p>}
        {working && (
          <p className="running">
            <span className="spinner" aria-hidden="true" /> {run.status === "queued" ? "Waiting for the worker…" : "Reading charts. This can take a minute or more per report; the first run also loads the models."}
          </p>
        )}
        {run?.status === "failed" && (
          <div className="error" role="alert">
            <strong>The verifier could not finish.</strong>
            <div className="small">{run.error}</div>
          </div>
        )}
        {run?.status === "done" && sum && (
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
              {sum.figures} figures · {sum.sentences} sentences · {sum.tool_calls} tool calls · {sum.seconds}s · policy <code>{sum.policy}</code> · parser <code>{sum.parser}</code> · tools{" "}
              <code>{sum.tools.join(", ")}</code> · finished {when(run.finished_at)}
            </p>
          </>
        )}
      </section>

      {run?.status === "done" && (
        <section className="card">
          <div className="section-head">
            <h2>2. Check the findings</h2>
          </div>
          <p className="muted">
            Open a finding to see the chart, each tool's reading and the reasoning. Confirm the ones that are real issues: only confirmed findings are sent to the student. "Not sure" means the verifier could not decide and is asking you.
          </p>
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
              <ClaimCard key={c.id} claim={c} runId={run.id} figures={run.figures} locked={closed} onChange={(u) => setRun((r) => ({ ...r, claims: r.claims.map((x) => (x.id === u.id ? u : x)) }))} />
            ))}
          </ul>
        </section>
      )}

      <section className="card">
        <div className="section-head">
          <h2>3. Send the review</h2>
        </div>
        {closed ? (
          <p className="muted">{s.status === "accepted" ? "This report was accepted." : "Rework was requested. Waiting for the student's new upload."}</p>
        ) : (
          <>
            <div className="row">
              <label>
                Score (0–100, optional)
                <input id="score" type="number" min="0" max="100" step="0.5" value={score} onChange={(e) => setScore(e.target.value)} />
              </label>
              <div className="grow confirmed-count">
                {confirmed.length} confirmed finding{confirmed.length === 1 ? "" : "s"} will be attached.
                {confirmed.length > 0 && (
                  <button className="btn ghost" type="button" onClick={insertConfirmed}>
                    Copy them into the findings text
                  </button>
                )}
              </div>
            </div>
            <label>
              Findings for the student
              <textarea id="findings" rows={6} value={findings} onChange={(e) => setFindings(e.target.value)} maxLength={10000} placeholder="What is right, what needs to change." />
            </label>
            <div className="row end">
              <button className="btn" disabled={busy || working} onClick={() => send("rework")}>
                Request rework
              </button>
              <button className="btn primary" disabled={busy || working} onClick={() => send("accepted")}>
                Accept and send
              </button>
            </div>
          </>
        )}
        <ErrorNote error={actionError} />
      </section>

      <h2>History</h2>
      <ol className="versions">
        {[...s.versions].reverse().map((v) => (
          <li key={v.id} className="card">
            <div className="version-head">
              <strong>Upload {v.version}</strong>
              <span className="muted small">
                {v.filename} · {when(v.uploaded_at)} · {v.runs.length} verifier run{v.runs.length === 1 ? "" : "s"}
              </span>
              <span className="spacer" />
              <button className="btn" onClick={() => openPdf(v.id).catch((e) => setActionError(e.message))}>
                Open PDF
              </button>
            </div>
            {v.note && <p className="muted">Student's note: {v.note}</p>}
            {v.reviews.length === 0 && <p className="muted">No review sent.</p>}
            {v.reviews.map((r) => (
              <ReviewCard key={r.id} review={r} />
            ))}
          </li>
        ))}
      </ol>
    </>
  );
}
