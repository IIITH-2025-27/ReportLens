import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { Crumbs, Due, ErrorNote, StatusBadge, VERDICT_ORDER, VerdictBadge, when } from "../components/bits";

const FILTERS = [
  ["open", "Needs action"],
  ["submitted", "Waiting"],
  ["verified", "Verified"],
  ["rework_requested", "Rework requested"],
  ["accepted", "Accepted"],
  ["all", "All"],
];
const OPEN = ["submitted", "verifying", "verified"];
const match = (f, r) => (f === "all" ? true : f === "open" ? OPEN.includes(r.status) : r.status === f);

export default function TAAssignment() {
  const { id } = useParams();
  const [a, setA] = useState(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("open");

  useEffect(() => {
    let live = true; // a response that arrives after this page has moved on is dropped
    api.assignment(id)
      .then((d) => live && setA(d))
      .catch((e) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [id]);

  const rows = a?.submissions || [];
  const shown = useMemo(() => rows.filter((r) => match(filter, r)), [rows, filter]);

  if (error) return <ErrorNote error={error} />;
  if (!a) return <p className="muted">Loading…</p>;

  return (
    <>
      <Crumbs course={a.course} />
      <h1>{a.title}</h1>
      <p className="muted">
        <Due at={a.due_at} /> · {a.submitted} of {a.students} students have submitted
      </p>
      {a.description && <p className="findings">{a.description}</p>}

      <h2 style={{ marginTop: 20 }}>Submitted reports</h2>
      <div className="filters" role="group" aria-label="Filter by status">
        {FILTERS.map(([key, label]) => (
          <button key={key} className={`chip ${filter === key ? "on" : ""}`} aria-pressed={filter === key} onClick={() => setFilter(key)}>
            {label} <span className="count">{rows.filter((r) => match(key, r)).length}</span>
          </button>
        ))}
      </div>
      {shown.length === 0 && <p className="empty">{rows.length === 0 ? "No student has submitted a report for this assignment yet." : "No reports with this status."}</p>}
      {shown.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Student</th>
                <th>Status</th>
                <th>Verifier result</th>
                <th>Score</th>
                <th>Uploads</th>
                <th>Last update</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link to={`/reports/${r.id}`}>{r.student.name}</Link>
                    <div className="muted small">{r.student.email}</div>
                  </td>
                  <td>
                    <StatusBadge status={r.status} /> {r.late && <span className="badge warn">Late</span>}
                  </td>
                  <td>
                    {!r.latest_run && <span className="muted">Not run</span>}
                    {r.latest_run && r.latest_run.status !== "done" && <span className="muted">{r.latest_run.status}</span>}
                    {r.latest_run?.verdicts && (
                      <span className="mini-verdicts">
                        {VERDICT_ORDER.filter((v) => v !== "SKIPPED" && r.latest_run.verdicts[v]).map((v) => (
                          <span key={v}>
                            <VerdictBadge verdict={v} /> {r.latest_run.verdicts[v]}
                          </span>
                        ))}
                      </span>
                    )}
                  </td>
                  <td className="num">{r.latest_score ?? "–"}</td>
                  <td className="num">{r.versions}</td>
                  <td>{when(r.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {a.missing.length > 0 && (
        <details className="card">
          <summary>Not submitted yet ({a.missing.length})</summary>
          <ul className="people">
            {a.missing.map((m) => (
              <li key={m.email}>
                <div>
                  {m.name || <span className="muted">Not signed up yet</span>}
                  <div className="muted small">{m.email}</div>
                </div>
              </li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}
