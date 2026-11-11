import { useEffect, useState } from "react";
import { api } from "../api";
import { VerdictBadge, num } from "./bits";

function FigureImage({ runId, figureId, caption }) {
  const [url, setUrl] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    let made;
    api
      .figure(runId, figureId)
      .then((blob) => {
        made = URL.createObjectURL(blob);
        if (alive) setUrl(made);
      })
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
      if (made) URL.revokeObjectURL(made);
    };
  }, [runId, figureId]);
  if (failed) return <p className="muted small">The figure image is not available.</p>;
  if (!url) return <p className="muted small">Loading figure…</p>;
  return (
    <figure className="fig">
      <img src={url} alt={caption || figureId} />
      {caption && <figcaption className="muted small">{caption}</figcaption>}
    </figure>
  );
}

// Where the gap falls against the two margins. Drawn to scale when all three numbers exist.
function GapBar({ gap, accept, flag }) {
  if (gap === null || accept === null || flag === null || !(flag > 0)) return null;
  const max = Math.max(flag * 1.6, gap * 1.15);
  const pct = (v) => `${Math.min(100, (v / max) * 100)}%`;
  return (
    <div className="gapbar" role="img" aria-label={`Gap ${num(gap)}; accepted up to ${num(accept)}; flagged above ${num(flag)}`}>
      <div className="track">
        <span className="zone ok" style={{ width: pct(accept) }} />
        <span className="zone warn" style={{ left: pct(accept), width: `calc(${pct(flag)} - ${pct(accept)})` }} />
        <span className="zone bad" style={{ left: pct(flag), right: 0 }} />
        <span className="marker" style={{ left: pct(gap) }} />
      </div>
      <div className="muted small">
        Gap {num(gap)} · accepted up to {num(accept)} · flagged above {num(flag)}
      </div>
    </div>
  );
}

export default function ClaimCard({ claim, runId, figures, onChange, locked }) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState(claim.ta_note || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const c = claim.claim;
  const tol = claim.tolerance ?? 0;
  const fig = claim.figure_id ? figures[claim.figure_id] : null;

  async function decide(ta_decision) {
    setBusy(true);
    setError("");
    try {
      onChange(await api.decideClaim(claim.id, { ta_decision, ta_note: note }));
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  }

  return (
    <li className={`claim ${open ? "open" : ""}`}>
      <button className="claim-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <VerdictBadge verdict={claim.verdict} />
        <span className="sentence">{claim.sentence}</span>
        <span className="claim-meta muted small">
          p.{claim.page + 1}
          {claim.figure_id && ` · ${claim.figure_id}`}
        </span>
        {claim.ta_decision && <span className={`badge ${claim.ta_decision === "confirmed" ? "bad" : "mute"}`}>{claim.ta_decision === "confirmed" ? "You confirmed" : "You dismissed"}</span>}
      </button>

      {open && (
        <div className="claim-body">
          <div className="claim-grid">
            <div>
              <dl className="facts">
                <dt>Claimed</dt>
                <dd>
                  {num(claim.claimed_value)}
                  {c?.relation === "greater" && " (more than)"}
                  {c?.relation === "less" && " (less than)"}
                  {c && c.relation === "approx" && <span className="muted"> ± {num(tol)} rounding</span>}
                </dd>
                <dt>Chart reads</dt>
                <dd>{num(claim.estimate)}</dd>
                {c && (
                  <>
                    <dt>Parsed as</dt>
                    <dd>
                      {c.claim_type.replace("_", " ")}: {c.series}
                      {c.series_b && c.series_b !== c.series && ` vs ${c.series_b}`} at {c.x}
                      {c.x_b && ` → ${c.x_b}`}
                    </dd>
                  </>
                )}
                <dt>Why</dt>
                <dd>{claim.reason || "–"}</dd>
                {claim.p_value !== null && (
                  <>
                    <dt>p-value</dt>
                    <dd>{num(claim.p_value, 4)}</dd>
                  </>
                )}
              </dl>
              <GapBar gap={claim.gap} accept={claim.margin_accept !== null && claim.margin_accept !== undefined ? tol + claim.margin_accept : null} flag={claim.margin_flag !== null ? tol + claim.margin_flag : null} />

              {Object.keys(claim.tool_values).length > 0 && (
                <table className="readings">
                  <thead>
                    <tr>
                      <th>Tool</th>
                      <th>Reading</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(claim.tool_values).map(([tool, v]) => (
                      <tr key={tool}>
                        <td>
                          <code>{tool}</code>
                        </td>
                        <td className="num">{num(v, 4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {claim.readings.some((r) => !r.ok) && (
                <p className="muted small">
                  Failed reads:{" "}
                  {claim.readings
                    .filter((r) => !r.ok)
                    .map((r) => `${r.tool} (${r.error})`)
                    .join(", ")}
                </p>
              )}
            </div>
            <div>{fig ? <FigureImage runId={runId} figureId={claim.figure_id} caption={fig.caption} /> : <p className="muted small">No figure was matched to this sentence.</p>}</div>
          </div>

          {claim.stages.length > 0 && (
            <details className="stages">
              <summary>How the verifier got here ({claim.stages.length} steps)</summary>
              <ol>
                {claim.stages.map((s, i) => (
                  <li key={i}>
                    <strong>{s.stage}</strong>: {String(s.decision)}
                    {s.result !== undefined && s.result !== null && <span className="muted"> → {String(s.result)}</span>}
                    {s.why && <div className="muted small">{s.why}</div>}
                  </li>
                ))}
              </ol>
            </details>
          )}

          <div className="decide">
            <label className="grow">
              Note for the student (shown only if you confirm)
              <input id={`note-${claim.id}`} value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} disabled={locked} placeholder="The chart shows about 78%, not 87%" />
            </label>
            <button className={`btn ${claim.ta_decision === "confirmed" ? "danger on" : "danger"}`} disabled={busy || locked} onClick={() => decide("confirmed")}>
              Confirm issue
            </button>
            <button className={`btn ${claim.ta_decision === "dismissed" ? "on" : ""}`} disabled={busy || locked} onClick={() => decide("dismissed")}>
              Dismiss
            </button>
            {claim.ta_decision && (
              <button className="btn ghost" disabled={busy || locked} onClick={() => decide(null)}>
                Clear
              </button>
            )}
          </div>
          {error && <p className="error">{error}</p>}
        </div>
      )}
    </li>
  );
}
