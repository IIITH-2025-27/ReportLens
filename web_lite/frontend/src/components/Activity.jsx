import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { VerdictBadge, isActive, verdictLabel } from "./bits";

// The agent's activity feed for one run, worded for a reader: what it understood, which chart it chose, which
// tools it called and why, what each read, and how it decided. Steps are grouped by the sentence being checked.
// While the run is going it asks for new steps every second; a finished run's feed is fetched once.

const TOOLS = {
  ocr_pixel: "OCR + pixel measurement",
  deplot: "DePlot (chart → table)",
  vlm_table: "Qwen3-VL (chart → table)",
  vlm_crop: "Qwen3-VL (zoomed crop)",
  vlm2_table: "second VLM (chart → table)",
  vlm2_crop: "second VLM (zoomed crop)",
  sim_deplot: "simulated DePlot",
  sim_vlm_table: "simulated VLM table",
  sim_vlm_crop: "simulated VLM crop",
};
const toolName = (t) => TOOLS[t] || t;
const CHART = { line: "line chart", bar: "bar chart", grouped_bar: "grouped bar chart", scatter: "scatter plot", unknown: "chart" };
const STATUS = {
  CONSISTENT: "so far it agrees with the sentence",
  MISMATCH_CANDIDATE: "so far it disagrees with the sentence",
  UNCLEAR: "still unclear, another reading is needed",
  TOO_FEW: "not enough readings yet",
};
const ERRORS = {
  series_not_found: "could not find that series on the chart",
  x_not_found: "could not find that x value on the chart",
  ocr_failed: "could not read the axis labels",
  bad_json: "gave an answer it could not parse",
  no_axis: "could not find the axis",
};
const VERDICTS = new Set(["CONSISTENT", "MISMATCH", "NOT_SURE", "NO_FIGURE", "SKIPPED"]);

function n(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "–";
  const a = Math.abs(v);
  return Number(v).toLocaleString(undefined, { maximumFractionDigits: a >= 100 ? 1 : a >= 1 ? 2 : 4 });
}
const clock = (s) => (s < 60 ? `${s.toFixed(1)}s` : `${Math.floor(s / 60)}m ${String(Math.round(s % 60)).padStart(2, "0")}s`);
const list = (xs) => (xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);
const unitOf = (u) => (u === "percent" ? "%" : u === "pct_points" ? " points" : "");

// "fig2" -> "Figure 2", using the plan events (they carry each figure's number)
function namer(figures) {
  return (id) => {
    const f = figures[id];
    return f?.number ? `Figure ${f.number}${f.panel || ""}` : id;
  };
}

// Make the agent's own reasons readable: tool and figure names, situation keys, raw score lists.
function plain(text, figName) {
  if (!text) return "";
  return text
    .replace(/'([a-z_]+)\|([a-z]+)' chart/g, (_, kind, level) => `${level} ${CHART[kind] || kind.replace(/_/g, " ")}`)
    .replace(/\s*\(scores \[.*?\]\)/g, "")
    .replace(/;\s*chart looks like:.*$/, "")
    .replace(/\b(vlm2_table|vlm2_crop|vlm_table|vlm_crop|ocr_pixel|deplot|sim_\w+)\+(vlm2_table|vlm2_crop|vlm_table|vlm_crop|ocr_pixel|deplot|sim_\w+)\b/g, (_, a, b) => `${toolName(a)} and ${toolName(b)}`)
    .replace(/\b(vlm2_table|vlm2_crop|vlm_table|vlm_crop|ocr_pixel|deplot|sim_\w+)\b/g, (t) => toolName(t))
    .replace(/\bfig(\d+)([a-z]?)\b/g, (id) => figName(id))
    .replace(/_/g, " ");
}

// The planner's reason is one clause per consideration, joined by ";" and often with its own numbers in brackets.
// The first clause is the decision ("best pair ... first"), the rest is supporting detail, shown on hover.
function shortWhy(why) {
  const first = why.split(/;\s*/)[0].replace(/\s*\((?:[^()]|\([^()]*\))*\)/g, "").trim();
  return first.length < why.length ? `${first}…` : first;
}

function claimText(d) {
  const u = unitOf(d.unit);
  const v = `${n(d.claimed)}${u}`;
  if (d.claim_type === "point") {
    const rel = d.relation === "greater" ? "above " : d.relation === "less" ? "below " : d.relation === "between" ? "between " : "";
    const high = d.relation === "between" && d.claimed_high != null ? ` and ${n(d.claimed_high)}${u}` : "";
    return `${d.series} at ${d.x} is ${rel}${v}${high}`;
  }
  if (d.claim_type === "difference") {
    const [[s1, x1], [s2, x2]] = d.operands;
    return `${s1} at ${x1} vs ${s2 === s1 ? "" : `${s2} `}at ${x2} differ by ${v}`;
  }
  if (d.claim_type === "relative_change") return `${d.series} changes by ${v} (relative) from ${d.x} to ${d.x_b}`;
  if (d.claim_type === "peak") return `${d.series} is highest at ${d.x}`;
  return `${d.series} at ${d.x}: ${v}`;
}

function readingText(d, claimType) {
  const raw = (d.raw || []).filter((x) => x !== null && x !== undefined).map(n);
  if (claimType === "difference") return `difference ${n(d.value)}${raw.length === 2 ? ` (read ${raw[0]} and ${raw[1]})` : ""}`;
  if (claimType === "relative_change") return `relative change ${n(d.value)}${raw.length === 2 ? ` (read ${raw[0]} → ${raw[1]})` : ""}`;
  if (claimType === "peak") return `gap to the highest other point ${n(d.value)}`;
  return `reads ${n(d.value)}`;
}

// One step -> { title, lines[], tone, badge }
function describe(r, figName, showWhy) {
  const d = r.detail || {};
  const why = showWhy && r.why ? plain(r.why, figName) : null;
  switch (r.stage) {
    case "run": {
      if (r.text.startsWith("load the verifier")) return { title: "Loading the verifier and its models", lines: [r.status === "start" ? "first run after the server started" : null] };
      if (r.text === "verifier ready") return { title: "Verifier ready", lines: [r.why ? plain(r.why.replace(/^policy (\w+), parser (\w+), tools /, "policy $1 · parser $2 · tools: "), figName) : null] };
      if (r.text.startsWith("read the PDF")) return { title: "Read the PDF: text, figures and axes", lines: [r.result || r.why] };
      if (r.text.startsWith("batch check")) return { title: "Final check across all the report's claims", lines: [r.why] };
      if (r.text === "finished") return { title: "Finished", lines: [r.why?.replace(/,?\s*\b\d+ SKIPPED\b,?/, (m) => (m.startsWith(",") && m.endsWith(",") ? "," : "")).replace(/^\s*,\s*/, "").replace(/\b(\d+) (CONSISTENT|MISMATCH|NOT_SURE|NO_FIGURE)\b/g, (_, k, v) => `${k} ${verdictLabel(v).toLowerCase()}`)], tone: "ok" };
      if (r.status === "error") return { title: "The verifier could not finish", lines: [r.why], tone: "bad" };
      return { title: r.text, lines: [r.why] };
    }
    case "plan": {
      if (!d.figure) return { title: plain(r.text, figName), lines: [why] };
      const lines = [];
      if (d.callable) lines.push(d.callable.length ? `Will read it with: ${list(d.callable.map(toolName))}` : "No tool is trusted on charts like this");
      const skipped = Object.entries(d.skipped || {});
      if (skipped.length) lines.push(`Not used here: ${skipped.map(([t, a]) => (a == null ? toolName(t) : `${toolName(t)} (answers only ${Math.round(a * 100)}% of the time on charts like this)`)).join("; ")}`);
      if (d.pairs?.length) lines.push(`Pairs that can cross-check each other: ${d.pairs.map((p) => (Array.isArray(p) ? p : String(p).split("~")).map(toolName).join(" + ")).join("; ")}`);
      return { title: `${figName(d.figure)}: ${d.looks_like || CHART[d.chart_type] || "chart"}`, lines };
    }
    case "parse": {
      if (r.text.startsWith("skip")) return { title: "Skipped: no result claim in this sentence", tone: "mute" };
      if (d.claim_type) {
        const lines = [d.parser === "llm" ? "Read by the language model" : "Read by the phrasing rules"];
        if (d.tolerance) lines.push(`Rounding allowed: ±${n(d.tolerance)}`);
        return { title: `Understood: ${claimText(d)}`, lines };
      }
      if (r.text === "escalate to LLM parser") return { title: "The phrasing rules did not recognise it, so the language model reads it", lines: [why] };
      if (r.text === "not a chart claim") return { title: "Not a claim about a chart", lines: [why], tone: "mute" };
      if (r.text === "alias") return { title: "Recognised a different name for a series", lines: [why] };
      if (r.text === "direction read from the sentence") return { title: "Read the direction from the wording", lines: [why] };
      return { title: plain(r.text, figName), lines: [why] };
    }
    case "figure": {
      const cands = (d.candidates || []).filter(([id]) => id);
      const scores = cands.length > 1 ? `Text-match scores: ${cands.map(([id, s]) => `${figName(id)} ${n(s)}`).join(" · ")}` : null;
      if (r.text === "NO_FIGURE") return { title: "No figure shows this value", lines: [why, scores], tone: "warn" };
      if (r.text === "re-parse with LLM") return { title: "No figure fits, so the language model re-reads the sentence", lines: [why] };
      const chosen = d.chosen?.length ? d.chosen : [r.text];
      const title = r.text.startsWith("check both") ? `Two figures fit; checking both: ${list(chosen.map(figName))}` : `Matched to ${list(chosen.map(figName))}`;
      return { title, lines: [why, scores] };
    }
    case "tool": {
      const lines = [];
      if (r.status === "start") lines.push("Reading…");
      else if (r.status === "error") lines.push(`Could not read: ${ERRORS[r.end?.error] || plain(r.end?.error || r.result || "", figName)}`);
      else if (r.end) {
        lines.push(`${readingText(r.end, d.claim_type || r.end.claim_type)}${r.end.status ? `; with ${r.end.readings} reading${r.end.readings === 1 ? "" : "s"} ${STATUS[r.end.status] || r.end.status}` : ""}`);
      } else if (r.result) lines.push(plain(r.result, figName));
      if (why) lines.push({ text: `Why this tool: ${shortWhy(why)}`, full: why });
      const where = d.figures ? ` on ${list(d.figures.map(figName))}` : "";
      const pts = d.operands ? ` · ${d.operands.map(([s, x]) => `${s} at ${x}`).join(", ")}` : "";
      return { title: `${toolName(r.tool)}${where}${pts}`, lines, tone: r.status === "error" ? "bad" : undefined, meta: r.end ? (r.end.cached ? "from cache" : r.seconds !== undefined ? clock(r.seconds) : null) : null };
    }
    case "repair":
      return { title: `Repairing ${toolName(r.tool)}`, lines: [plain(r.text, figName), r.result ? plain(r.result, figName) : null] };
    case "stop": {
      const kind = (r.text.match(/^stop reading \((\w+)\)$/) || [])[1];
      const title = kind === "handoff" ? "Stopped reading: this one goes to the TA" : kind === "stop" ? "Stopped reading: enough evidence" : plain(r.text, figName);
      return { title, lines: [why], tone: "mute" };
    }
    case "decide": {
      const v = d.verdict || (VERDICTS.has(r.text) ? r.text : null);
      const lines = [];
      if (d.reused) lines.push("Same sentence as an earlier one: its answer is reused, no new readings");
      else if (d.handed_off) lines.push(`Handed to the TA: ${plain(r.why, figName)}`);
      else if (d.estimate != null && d.claimed != null) {
        const u = unitOf(d.unit);
        const gap = d.gap != null ? `off by ${n(d.gap)}${u}` : "";
        if (v === "MISMATCH") lines.push(`The chart gives ${n(d.estimate)}${u}, the sentence says ${n(d.claimed)}${u}: ${gap}, more than the ${n(d.margin_flag)} allowed`);
        else if (v === "CONSISTENT") lines.push(`The chart gives ${n(d.estimate)}${u}, the sentence says ${n(d.claimed)}${u}: ${gap}, within the ${n(d.margin_accept)} allowed`);
        else lines.push(`The chart gives ${n(d.estimate)}${u}, the sentence says ${n(d.claimed)}${u}${gap ? ` (${gap})` : ""}: ${plain(r.why, figName)}`);
        const tv = Object.entries(d.tool_values || {});
        if (tv.length) lines.push(`Per tool: ${tv.map(([t, x]) => `${toolName(t)} ${n(x)}`).join(" · ")}`);
      } else if (r.why) lines.push(plain(r.why.replace(/^handed off: /, "Handed to the TA: "), figName));
      return { title: "Verdict", badge: v, lines };
    }
    default:
      return { title: plain(r.text, figName), lines: [why] };
  }
}

// A tool call arrives as two events (start, then ok / error): fold them into one step that knows how long it took.
function toRows(events) {
  const rows = [];
  for (const e of events) {
    if (e.status === "ok" || e.status === "error") {
      const open = rows.findLast((r) => r.status === "start" && r.stage === e.stage && r.text === e.text);
      if (open) {
        open.status = e.status;
        open.result = e.why;
        open.end = e.detail || null;
        open.seconds = (new Date(e.at) - new Date(open.at)) / 1000;
        continue;
      }
    }
    rows.push({ ...e, end: null });
  }
  // a run step ("loading the models") has no end event of its own: anything after it means it finished
  rows.forEach((r, i) => {
    if (r.stage === "run" && r.status === "start" && i < rows.length - 1) r.status = "ok";
  });
  return rows;
}

// Setup steps first, then one group per sentence in the order the agent first looked at it.
function toGroups(rows) {
  const setup = { key: "__setup", sentence: null, rows: [] };
  const by = new Map();
  for (const r of rows) {
    if (r.stage === "claim") continue; // the parse step already says what is being checked
    if (!r.sentence) {
      setup.rows.push(r);
      continue;
    }
    if (!by.has(r.sentence)) by.set(r.sentence, { key: r.sentence, sentence: r.sentence, rows: [] });
    by.get(r.sentence).rows.push(r);
  }
  const groups = [...by.values()].map((g) => {
    const decide = g.rows.findLast((r) => r.stage === "decide");
    const verdict = decide ? decide.detail?.verdict || (VERDICTS.has(decide.text) ? decide.text : null) : null;
    const skipped = verdict === "SKIPPED" || g.rows.every((r) => r.stage === "parse" && (r.text.startsWith("skip") || r.text === "not a chart claim"));
    const noFigure = g.rows.some((r) => r.stage === "figure" && r.text === "NO_FIGURE");
    return {
      ...g,
      verdict: verdict || (noFigure ? "NO_FIGURE" : skipped ? "SKIPPED" : null),
      skipped,
      calls: g.rows.filter((r) => r.stage === "tool").length,
      pending: g.rows.some((r) => r.status === "start"),
      seconds: g.rows.reduce((a, r) => a + (r.seconds || 0), 0),
    };
  });
  return { setup, groups };
}

export default function Activity({ runId, status }) {
  const [events, setEvents] = useState([]);
  const [error, setError] = useState("");
  const [showWhy, setShowWhy] = useState(true);
  const [open, setOpen] = useState(isActive(status)); // the whole panel: open while running, then as the reader left it
  const [opened, setOpened] = useState({}); // group key -> open / closed, once the reader has toggled it
  const last = useRef(0);
  const box = useRef(null);
  const stick = useRef(true); // follow new steps unless the reader has scrolled up
  const active = isActive(status);

  useEffect(() => {
    setEvents([]);
    setOpened({});
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
  }, [events]);

  const figures = useMemo(() => Object.fromEntries(events.filter((e) => e.stage === "plan" && e.detail?.figure).map((e) => [e.detail.figure, e.detail])), [events]);
  const figName = useMemo(() => namer(figures), [figures]);
  const { setup, groups } = useMemo(() => toGroups(toRows(events)), [events]);

  if (!active && !events.length) {
    return error ? <p className="error small">{error}</p> : <p className="muted small">No activity was recorded for this run (it ran before the activity feed was added).</p>;
  }

  const claims = groups.filter((g) => !g.skipped);
  const decided = claims.filter((g) => g.verdict).length;
  const calls = groups.reduce((a, g) => a + g.calls, 0);
  const t0 = events.length ? new Date(events[0].at) : null;
  const elapsed = t0 ? (new Date(events[events.length - 1].at) - t0) / 1000 : 0;
  const current = active ? [...claims].reverse().find((g) => g.pending || !g.verdict) : null;
  const shown = claims; // sentences with a number that are not a chart claim are not listed
  const isOpen = (g) => opened[g.key] ?? (active ? g === current || g.key === "__setup" && !claims.length : false);
  const toggle = (g) => setOpened((o) => ({ ...o, [g.key]: !isOpen(g) }));
  const setAll = (value) => setOpened(Object.fromEntries([setup, ...shown].map((g) => [g.key, value])));

  function Step({ r }) {
    let s;
    try {
      s = describe(r, figName, showWhy);
    } catch {
      s = { title: r.text, lines: [r.result, r.why] }; // never let one unexpected step blank the page
    }
    const pending = r.status === "start";
    const lines = (s.lines || []).filter(Boolean);
    return (
      <li className={`step step-${r.stage} ${s.tone ? `tone-${s.tone}` : ""}`}>
        <span className="step-dot" aria-hidden="true">
          {pending ? active ? <span className="spinner" /> : "…" : r.status === "error" ? "✕" : r.status === "ok" ? "✓" : ""}
        </span>
        <div className="step-body">
          <div className="step-title">
            {s.badge ? <VerdictBadge verdict={s.badge} /> : <span>{s.title}</span>}
            {s.meta && <span className="step-meta">{s.meta}</span>}
            {pending && !active && <span className="step-meta">did not finish</span>}
          </div>
          {lines.map((l, i) => (
            <div key={i} className={i === 0 && r.stage !== "decide" ? "step-line" : "step-line muted"} title={l.full || undefined}>
              {l.text || l}
            </div>
          ))}
        </div>
        <span className="step-time">{t0 ? `+${clock((new Date(r.at) - t0) / 1000)}` : ""}</span>
      </li>
    );
  }

  function Group({ g, title, index }) {
    const o = isOpen(g);
    return (
      <li className={`agroup ${g.skipped ? "agroup-skipped" : ""} ${g === current ? "agroup-current" : ""}`}>
        <button type="button" className="agroup-head" aria-expanded={o} onClick={() => toggle(g)}>
          <span className="agroup-caret" aria-hidden="true">{o ? "▾" : "▸"}</span>
          <span className="agroup-title">
            {index != null && <span className="agroup-n">{index}</span>}
            {title}
          </span>
          <span className="agroup-side">
            {g === current && <span className="spinner" aria-label="working on it" />}
            {g.calls > 0 && <span className="muted small">{g.calls} tool call{g.calls === 1 ? "" : "s"}</span>}
            {g.verdict && <VerdictBadge verdict={g.verdict} />}
          </span>
        </button>
        {o && (
          <ol className="steps">
            {g.rows.map((r) => (
              <Step key={r.seq} r={r} />
            ))}
          </ol>
        )}
      </li>
    );
  }

  return (
    <details className="activity" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>
        Agent activity{" "}
        <span className="muted">
          · {claims.length ? `${decided} of ${claims.length} claims decided` : "starting"} · {calls} tool call{calls === 1 ? "" : "s"} · {clock(elapsed)}
        </span>
      </summary>

      {active && (
        <p className="activity-now small" aria-live="polite">
          <span className="spinner" aria-hidden="true" />{" "}
          {current ? <>Checking: “{current.sentence}”</> : setup.rows.length ? describe(setup.rows[setup.rows.length - 1], figName, false).title : "Starting…"}
        </p>
      )}

      <div className="activity-tools small">
        <label title="Each step's reason, as the agent logged it: why it picked this figure or tool, why it stopped">
          <input type="checkbox" checked={showWhy} onChange={(e) => setShowWhy(e.target.checked)} /> Show the agent's reasons
        </label>
        <span className="spacer" />
        <button type="button" className="btn ghost" onClick={() => setAll(true)}>
          Expand all
        </button>
        <button type="button" className="btn ghost" onClick={() => setAll(false)}>
          Collapse all
        </button>
      </div>

      <ol
        className="agroups"
        ref={box}
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
        }}
      >
        {setup.rows.length > 0 && <Group g={setup} title="Setup: reading the report and planning each figure" />}
        {shown.map((g) => (
          <Group key={g.key} g={g} index={g.skipped ? null : claims.indexOf(g) + 1} title={`“${g.sentence}”`} />
        ))}
      </ol>
      {error && <p className="error small">{error}</p>}
    </details>
  );
}
