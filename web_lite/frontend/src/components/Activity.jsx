import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { VerdictBadge, isActive } from "./bits";

// The agent's activity feed for one run: every step it took, in order, with the reason it gave.
// While the run is going it asks for new steps every second; a finished run's feed is fetched once.
const STAGE = {
  run: "Run",
  plan: "Plan",
  parse: "Parse",
  figure: "Figure",
  claim: "Claim",
  tool: "Tool",
  repair: "Repair",
  stop: "Stop",
  decide: "Decide",
};
const VERDICTS = new Set(["CONSISTENT", "MISMATCH", "NOT_SURE", "NO_FIGURE", "SKIPPED"]);

// A tool call arrives as two events (start, then ok / error): fold them into one row that shows how long it took.
function toRows(events) {
  const rows = [];
  for (const e of events) {
    if (e.status === "ok" || e.status === "error") {
      const open = rows.findLast((r) => r.status === "start" && r.stage === e.stage && r.text === e.text);
      if (open) {
        open.status = e.status;
        open.result = e.why;
        open.seconds = (new Date(e.at) - new Date(open.at)) / 1000;
        continue;
      }
    }
    rows.push({ ...e });
  }
  return rows;
}

const clock = (s) => (s < 60 ? `${s.toFixed(1)}s` : `${Math.floor(s / 60)}m ${String(Math.round(s % 60)).padStart(2, "0")}s`);

export default function Activity({ runId, status }) {
  const [events, setEvents] = useState([]);
  const [error, setError] = useState("");
  const [toolsOnly, setToolsOnly] = useState(false);
  const [open, setOpen] = useState(isActive(status)); // open while running; stays as the reader left it
  const last = useRef(0);
  const box = useRef(null);
  const stick = useRef(true); // follow new steps unless the reader has scrolled up
  const active = isActive(status);

  useEffect(() => {
    setEvents([]);
    last.current = 0;
    stick.current = true;
    setOpen(isActive(status));
  }, [runId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let live = true;
    let timer;
    async function pull() {
      try {
        const r = await api.events(runId, last.current);
        if (!live) return;
        if (r.events.length) {
          last.current = r.events[r.events.length - 1].seq;
          setEvents((old) => [...old, ...r.events]);
        }
        setError("");
        if (isActive(r.status)) timer = setTimeout(pull, 1000);
      } catch (e) {
        if (live) {
          setError(e.message);
          timer = setTimeout(pull, 3000);
        }
      }
    }
    pull();
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [runId, status]);

  useEffect(() => {
    if (stick.current && box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [events, toolsOnly]);

  const rows = useMemo(() => toRows(events), [events]);
  const t0 = events.length ? new Date(events[0].at) : null;
  const shown = toolsOnly ? rows.filter((r) => r.stage === "tool" || r.stage === "repair" || r.stage === "decide") : rows;
  const calls = rows.filter((r) => r.stage === "tool").length;

  if (!active && !events.length) {
    return error ? <p className="error small">{error}</p> : <p className="muted small">No activity was recorded for this run (it ran before the activity feed was added).</p>;
  }

  let lastSentence = null;
  return (
    <details className="activity" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>
        Agent activity <span className="muted">· {rows.length} steps · {calls} tool calls</span>
      </summary>
      <label className="activity-filter small">
        <input type="checkbox" checked={toolsOnly} onChange={(e) => setToolsOnly(e.target.checked)} /> Tool calls and verdicts only
      </label>
      <ol
        className="activity-log"
        ref={box}
        aria-live={active ? "polite" : undefined}
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
        }}
      >
        {shown.map((r) => {
          const header = r.sentence && r.sentence !== lastSentence ? r.sentence : null;
          if (r.sentence) lastSentence = r.sentence;
          const pending = r.status === "start";
          return (
            <li key={r.seq} className={`act act-${r.stage} ${r.status ? `act-${r.status}` : ""}`}>
              {header && <div className="act-sentence">“{header}”</div>}
              <div className="act-row">
                <span className="act-time">{t0 ? `+${clock((new Date(r.at) - t0) / 1000)}` : ""}</span>
                <span className="act-icon" aria-hidden="true">
                  {pending ? active ? <span className="spinner" /> : "…" : r.status === "error" ? "✕" : r.status === "ok" ? "✓" : "•"}
                </span>
                <span className="act-stage">{STAGE[r.stage] || r.stage}</span>
                <span className="act-text">
                  {r.stage === "decide" && VERDICTS.has(r.text) ? <VerdictBadge verdict={r.text} /> : r.text}
                  {r.seconds !== undefined && <span className="muted small"> · {clock(r.seconds)}</span>}
                  {pending && !active && <span className="muted small"> · did not finish</span>}
                </span>
              </div>
              {r.result && <div className={`act-result small ${r.status === "error" ? "act-bad" : ""}`}>{r.result}</div>}
              {r.why && <div className="act-why muted small">{r.result ? `why: ${r.why}` : r.why}</div>}
            </li>
          );
        })}
      </ol>
      {error && <p className="error small">{error}</p>}
    </details>
  );
}
