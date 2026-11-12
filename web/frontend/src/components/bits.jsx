// Small shared pieces: status and verdict labels, dates, numbers.
import { Link } from "react-router-dom";

const STATUS = {
  submitted: ["Waiting for TA", "wait"],
  verifying: ["Verifier running", "run"],
  verified: ["Verified, awaiting review", "info"],
  rework_requested: ["Rework requested", "warn"],
  accepted: ["Accepted", "ok"],
};
const STATUS_FOR_STUDENT = { verifying: ["With the TA", "info"], verified: ["With the TA", "info"] };

export function StatusBadge({ status, student = false }) {
  const [label, tone] = (student && STATUS_FOR_STUDENT[status]) || STATUS[status] || [status, "wait"];
  return <span className={`badge ${tone}`}>{label}</span>;
}

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

export function when(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function num(v, digits = 3) {
  if (v === null || v === undefined) return "–";
  return Number(v).toLocaleString(undefined, { maximumFractionDigits: digits });
}

export function ErrorNote({ error }) {
  return error ? (
    <p className="error" role="alert">
      {error}
    </p>
  ) : null;
}

// Courses > course > assignment trail shown above a page title.
export function Crumbs({ course, assignment }) {
  return (
    <p className="crumb">
      <Link to="/">Courses</Link>
      {course && (
        <>
          {" / "}
          <Link to={`/courses/${course.id}`}>{course.code || course.name}</Link>
        </>
      )}
      {assignment && (
        <>
          {" / "}
          <Link to={`/assignments/${assignment.id}`}>{assignment.title}</Link>
        </>
      )}
    </p>
  );
}

export function Due({ at }) {
  if (!at) return <span className="muted">No due date</span>;
  const past = new Date(at) < new Date();
  return <span className={past ? "muted" : ""}>Due {when(at)}</span>;
}
