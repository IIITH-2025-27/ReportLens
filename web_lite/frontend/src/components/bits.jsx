// Small shared pieces: verdict and run labels, dates, numbers. Labels match web/frontend.

const VERDICT = {
  CONSISTENT: ["Consistent", "ok"],
  MISMATCH: ["Mismatch", "bad"],
  NOT_SURE: ["Not sure", "warn"],
  NO_FIGURE: ["No matching figure", "wait"],
  SKIPPED: ["Not a chart claim", "mute"],
};
export const VERDICT_ORDER = ["MISMATCH", "NOT_SURE", "NO_FIGURE", "CONSISTENT", "SKIPPED"];
export const verdictLabel = (v) => (VERDICT[v] || [v])[0];

export function VerdictBadge({ verdict }) {
  const [label, tone] = VERDICT[verdict] || [verdict, "wait"];
  return <span className={`badge ${tone}`}>{label}</span>;
}

const RUN = { queued: ["Queued", "run"], running: ["Running", "run"], done: ["Done", "ok"], failed: ["Failed", "bad"] };
export function RunBadge({ status }) {
  const [label, tone] = RUN[status] || [status, "wait"];
  return <span className={`badge ${tone}`}>{label}</span>;
}

// MISMATCH 2 · NOT_SURE 1 ... for a run summary; chart claims only.
export function MiniVerdicts({ verdicts }) {
  const shown = VERDICT_ORDER.filter((v) => v !== "SKIPPED" && verdicts?.[v]);
  if (!shown.length) return <span className="muted small">No chart claims</span>;
  return (
    <span className="mini-verdicts">
      {shown.map((v) => (
        <span key={v}>
          <VerdictBadge verdict={v} /> {verdicts[v]}
        </span>
      ))}
    </span>
  );
}

export const isActive = (status) => status === "queued" || status === "running";

export function when(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function num(v, digits = 3) {
  if (v === null || v === undefined) return "–";
  return Number(v).toLocaleString(undefined, { maximumFractionDigits: digits });
}

export function size(bytes) {
  if (!bytes) return "";
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function ErrorNote({ error }) {
  return error ? (
    <p className="error" role="alert">
      {error}
    </p>
  ) : null;
}
